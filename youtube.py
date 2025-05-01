import os
import json
import subprocess
import wget
import time
import random
import logging
import sys
from tqdm import tqdm
from typing import List, Dict, Optional, Union, Tuple
from urllib.parse import urlparse, parse_qs

# 設置系統環境變數，解決中文編碼問題
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 在 Windows 系統上設置控制台編碼為 UTF-8
if os.name == 'nt':
    os.system('chcp 65001 > nul')

# 設置日誌
logging.basicConfig(
    filename='downloader.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)


class VideoDownloader:
    def __init__(self, base_folder: str = "./downloads"):
        self.base_folder = base_folder
        self.ytdlp_path = './yt-dlp.exe'  # Windows 版本

        # 格式映射，支援影片和音訊合併
        self.format_map = {
            '1': 'b[ext=mp4]',  # 最佳影片+音訊（MP4）
            '2': 'ba[ext=m4a]',  # 僅音訊
            '3': 'bestvideo[height<=1080]+bestaudio[ext=m4a]/best[height<=1080]',  # 1080p
            '4': 'bestvideo[height<=720]+bestaudio[ext=m4a]/best[height<=720]'   # 720p
        }

        # 支援的編碼列表，用於解碼 subprocess 輸出
        self.encodings_to_try = ['cp950', 'gbk', 'gb2312', 'utf-8']

    def ensure_folder_exists(self, folder_path: str) -> None:
        """確保資料夾存在，若不存在則建立。"""
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            print(f"已建立資料夾：{folder_path}")
            logging.info(f"已建立資料夾：{folder_path}")

    def download_ytdlp(self) -> bool:
        """下載 yt-dlp 可執行檔（若尚未存在）。"""
        if not os.path.exists(self.ytdlp_path):
            print('[正在下載 yt-dlp]')
            logging.info('開始下載 yt-dlp')
            try:
                wget.download(
                    'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe',
                    self.ytdlp_path
                )
                print("\nyt-dlp 下載完成")
                logging.info('yt-dlp 下載完成')
                return True
            except Exception as e:
                print(f"下載 yt-dlp 失敗：{e}")
                logging.error(f"下載 yt-dlp 失敗：{e}")
                return False
        return True

    def sanitize_filename(self, filename: str) -> str:
        """清理檔案名稱，移除無效字符並限制長度。"""
        if not filename or filename.isspace():
            return "未知標題"
        if not isinstance(filename, str):
            filename = str(filename)
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename.strip()[:200]

    def get_unique_filename(self, folder_path: str, title: str, ext: str) -> str:
        """檢查同名檔案，若存在則加上流水號。"""
        base_name = self.sanitize_filename(title)
        output_file = f"{folder_path}/{base_name}.{ext}"
        counter = 1
        while os.path.exists(output_file):
            output_file = f"{folder_path}/{base_name}_{counter}.{ext}"
            counter += 1
        return output_file

    def run_subprocess_with_encoding(self, cmd: List[str], description: str = "") -> Optional[subprocess.CompletedProcess]:
        """執行 subprocess 命令並處理編碼問題。"""
        print(f"執行命令：{' '.join(cmd)}")
        logging.info(f"執行命令：{' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=False
            )

            stdout_text = None
            stderr_text = None

            for encoding in self.encodings_to_try:
                try:
                    if stdout_text is None:
                        stdout_text = result.stdout.decode(encoding)
                    if stderr_text is None:
                        stderr_text = result.stderr.decode(encoding)
                    if stdout_text and stderr_text:
                        print(f"成功使用 {encoding} 編碼解析輸出")
                        logging.info(f"成功使用 {encoding} 編碼解析輸出")
                        break
                except UnicodeDecodeError:
                    continue

            if stdout_text is None:
                stdout_text = result.stdout.decode('utf-8', errors='replace')
            if stderr_text is None:
                stderr_text = result.stderr.decode('utf-8', errors='replace')

            decoded_result = subprocess.CompletedProcess(
                args=result.args,
                returncode=result.returncode,
                stdout=stdout_text,
                stderr=stderr_text
            )

            return decoded_result

        except Exception as e:
            print(f"執行命令時發生錯誤：{e}")
            logging.error(f"執行命令時發生錯誤：{e}")
            return None

    def get_video_info(self, video_url: str) -> Optional[Dict]:
        """取得單個影片的資訊。"""
        print(f"正在取得影片資訊：{video_url}")
        logging.info(f"正在取得影片資訊：{video_url}")

        try:
            cmd = [
                self.ytdlp_path,
                video_url,
                '--print', 'id',
                '--print', 'title',
                '--no-warnings',
                '--no-playlist',
                '--ignore-errors'
            ]

            result = self.run_subprocess_with_encoding(cmd, "取得影片資訊")

            if result is None:
                print("執行命令失敗，無法獲取結果")
                logging.error("執行命令失敗，無法獲取結果")
                return None

            if result.returncode != 0:
                print(f"取得影片資訊失敗，返回碼：{result.returncode}")
                print(f"錯誤輸出：{result.stderr}")
                logging.error(f"取得影片資訊失敗：{result.stderr}")
                return None

            output = result.stdout.strip() if result.stdout else ""
            if not output:
                print("命令執行成功但沒有輸出")
                logging.error("命令執行成功但沒有輸出")
                return None

            lines = output.split('\n')

            if len(lines) < 2 or not lines[0] or not lines[1]:
                print(f"輸出格式不符合預期：{output}")
                logging.error(f"輸出格式不符合預期：{output}")
                return None

            video_id = lines[0].strip()
            video_title = lines[1].strip()

            if video_id == 'NA' or video_title == 'NA':
                print(f"API 返回 NA 值，可能是影片不可用或地區限制")
                logging.error(f"API 返回 NA 值，可能是影片不可用或地區限制")
                return None

            video_info = {
                "link": video_url,
                "title": video_title,
                "id": video_id
            }

            print(f"成功取得影片資訊：{video_title}")
            logging.info(f"成功取得影片資訊：{video_title}")
            return video_info

        except Exception as e:
            print(f"處理影片資訊時發生錯誤：{e}")
            logging.error(f"處理影片資訊時發生錯誤：{e}")
            return None

    def get_playlist_info(self, playlist_url: str, limit: Optional[int] = None) -> Optional[Dict]:
        """取得播放清單資訊，包括標題和影片列表。"""
        print(f"正在取得播放清單資訊：{playlist_url}")
        logging.info(f"正在取得播放清單資訊：{playlist_url}")

        try:
            title_cmd = [
                self.ytdlp_path,
                playlist_url,
                '--get-filename',
                '-o', '%(playlist_title)s',
                '--no-simulate',
                '--flat-playlist',
                '--playlist-items', '1'
            ]

            result = self.run_subprocess_with_encoding(title_cmd, "取得播放清單標題")

            if result is None or result.returncode != 0:
                print(f"取得播放清單標題失敗：{result.stderr if result else 'N/A'}")
                logging.error(f"取得播放清單標題失敗：{result.stderr if result else 'N/A'}")
                playlist_title = "未知播放清單"
            else:
                playlist_title = result.stdout.strip() if result.stdout else "未知播放清單"
                if not playlist_title or playlist_title == 'NA':
                    playlist_title = "未知播放清單"

            print(f"獲取到播放清單標題: {playlist_title}")
            logging.info(f"獲取到播放清單標題: {playlist_title}")

        except Exception as e:
            print(f"取得播放清單標題時發生錯誤：{e}")
            logging.error(f"取得播放清單標題時發生錯誤：{e}")
            playlist_title = "未知播放清單"

        try:
            videos_cmd = [
                self.ytdlp_path,
                playlist_url,
                '--flat-playlist',
                '--print', 'id',
                '--print', 'title',
                '--no-warnings'
            ]

            if limit:
                videos_cmd.extend(['--playlist-items', f'1-{limit}'])

            videos_result = self.run_subprocess_with_encoding(videos_cmd, "取得播放清單影片")

            if videos_result is None:
                print("執行命令失敗，無法獲取結果")
                logging.error("執行命令失敗，無法獲取結果")
                return None

            videos = []
            stdout_content = videos_result.stdout if videos_result.stdout else ""
            lines = stdout_content.strip().split('\n')

            for i in range(0, len(lines), 2):
                if i + 1 < len(lines):
                    video_id = lines[i].strip()
                    video_title = lines[i + 1].strip()
                    videos.append({
                        "link": f"{playlist_url}",  # 對於非 YouTube，可能需要調整
                        "title": video_title,
                        "id": video_id
                    })

            if not videos:
                print("播放清單中沒有可訪問的影片")
                logging.error("播放清單中沒有可訪問的影片")
                return None

            playlist_info = {
                "title": playlist_title,
                "videos": videos
            }

            logging.info(f"成功取得播放清單資訊：{playlist_title}，包含 {len(videos)} 個影片")
            return playlist_info

        except Exception as e:
            print(f"處理播放清單時發生錯誤：{e}")
            logging.error(f"處理播放清單時發生錯誤：{e}")
            return None

    def save_playlist_json(self, playlist_info: Dict) -> str:
        """儲存播放清單資訊為 JSON 並返回資料夾路徑。"""
        playlist_title = self.sanitize_filename(playlist_info['title'])
        folder_path = os.path.join(self.base_folder, playlist_title)
        self.ensure_folder_exists(folder_path)

        json_path = os.path.join(folder_path, 'playlist.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(playlist_info['videos'], f, ensure_ascii=False, indent=2)

        video_count = len(playlist_info['videos'])
        print(f"已儲存 JSON 檔案，包含 {video_count} 個影片：{json_path}")
        logging.info(f"已儲存 JSON 檔案：{json_path}")

        return folder_path

    def download_single_video(self, video_info: Dict, format: str = 'b[ext=mp4]') -> None:
        """下載單個影片，使用影片標題作為檔案名稱。"""
        if not video_info:
            print("沒有影片資訊可用於下載")
            logging.error("沒有影片資訊可用於下載")
            return

        folder_path = os.path.join(self.base_folder, "單個影片")
        self.ensure_folder_exists(folder_path)

        title = video_info.get('title', '未知標題')
        ext = 'mp4' if 'mp4' in format else 'm4a'
        output_file = self.get_unique_filename(folder_path, title, ext)

        print(f"正在下載影片：{title}")
        logging.info(f"正在下載影片：{title}")

        cmd = [
            self.ytdlp_path,
            video_info['link'],
            '-f', format,
            '-o', output_file,
            '--progress',
            '--no-overwrites'
        ]

        try:
            result = self.run_subprocess_with_encoding(cmd, "下載單個影片")

            if result and result.returncode == 0:
                print(f'✓ 下載成功：{title}')
                print(f'儲存位置：{output_file}')
                logging.info(f'下載成功：{title}，儲存位置：{output_file}')
            else:
                stderr_msg = result.stderr if result and result.stderr else "未知錯誤"
                print(f'✗ 下載失敗：{title}\n錯誤：{stderr_msg}')
                logging.error(f'下載失敗：{title}，錯誤：{stderr_msg}')

        except Exception as e:
            print(f"下載影片時發生錯誤：{e}")
            logging.error(f"下載影片時發生錯誤：{e}")

    def load_download_log(self, log_path: str) -> List[str]:
        """載入已下載影片的記錄"""
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"載入下載記錄時發生錯誤：{e}")
                logging.error(f"載入下載記錄時發生錯誤：{e}")
                return []
        return []

    def save_download_log(self, log_path: str, video_ids: List[str]) -> None:
        """保存已下載影片的記錄"""
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(video_ids, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存下載記錄時發生錯誤：{e}")
            logging.error(f"保存下載記錄時發生錯誤：{e}")

    def download_videos(
        self,
        videos: List[Dict],
        folder_path: str,
        limit: Optional[int] = None,
        format: str = 'b[ext=mp4]',
        batch_size: int = 10,
        delay_min: float = 1.0,
        delay_max: float = 5.0,
        start_index: int = 0
    ) -> None:
        """分批下載影片，使用影片標題作為檔案名稱。"""
        if not videos:
            print("沒有影片可下載")
            logging.info("沒有影片可下載")
            return

        downloadable_videos = videos[start_index:] if start_index > 0 else videos
        videos_to_download = downloadable_videos[:limit] if limit and limit < len(downloadable_videos) else downloadable_videos
        print(f"將下載 {len(videos_to_download)}/{len(videos)} 個影片")
        logging.info(f"將下載 {len(videos_to_download)}/{len(videos)} 個影片")

        download_log_path = os.path.join(folder_path, 'download_log.json')
        downloaded_videos = self.load_download_log(download_log_path)

        for batch_start in range(0, len(videos_to_download), batch_size):
            batch = videos_to_download[batch_start:batch_start + batch_size]
            print(f"\n處理批次 {batch_start//batch_size + 1} ({batch_start + 1}-{min(batch_start + batch_size, len(videos_to_download))})")
            logging.info(f"處理批次 {batch_start//batch_size + 1} ({batch_start + 1}-{min(batch_start + batch_size, len(videos_to_download))})")

            for i, video in enumerate(tqdm(batch, desc="批次進度")):
                try:
                    link = video.get('link')
                    video_id = video.get('id')
                    if not video_id and 'v=' in link:
                        video_id = link.split('v=')[1].split('&')[0]

                    raw_title = video.get('title', '未知標題')

                    if video_id and video_id in downloaded_videos:
                        print(f"\n跳過已下載的視頻：{raw_title}")
                        logging.info(f"跳過已下載的視頻：{raw_title}")
                        continue

                    if not link:
                        print(f"錯誤：第 {batch_start + i + 1} 項缺少連結")
                        logging.error(f"第 {batch_start + i + 1} 項缺少連結")
                        continue

                    print(f"\n正在下載 ({batch_start + i + 1}/{len(videos_to_download)})：{raw_title}")
                    logging.info(f"正在下載 ({batch_start + i + 1}/{len(videos_to_download)})：{raw_title}")

                    ext = 'mp4' if 'mp4' in format else 'm4a'
                    output_file = self.get_unique_filename(folder_path, raw_title, ext)

                    cmd = [
                        self.ytdlp_path,
                        link,
                        '-f', format,
                        '-o', output_file,
                        '--progress',
                        '--no-overwrites'
                    ]

                    result = self.run_subprocess_with_encoding(cmd, f"下載影片 {batch_start + i + 1}/{len(videos_to_download)}")

                    if result and result.returncode == 0:
                        print(f'✓ 下載成功：{raw_title}')
                        logging.info(f'下載成功：{raw_title}')
                        if video_id:
                            downloaded_videos.append(video_id)
                            self.save_download_log(download_log_path, downloaded_videos)
                    else:
                        stderr_msg = result.stderr if result and result.stderr else "未知錯誤"
                        print(f'✗ 下載失敗：{raw_title}\n錯誤：{stderr_msg}')
                        logging.error(f'下載失敗：{raw_title}，錯誤：{stderr_msg}')

                    time.sleep(random.uniform(delay_min, delay_max))

                except Exception as e:
                    print(f"下載影片 {raw_title} 時發生錯誤：{e}")
                    logging.error(f"下載影片 {raw_title} 時發生錯誤：{e}")

            if batch_start + batch_size < len(videos_to_download):
                batch_pause = random.uniform(5.0, 10.0)
                print(f"在下一批次前暫停 {batch_pause:.2f} 秒...")
                logging.info(f"在下一批次前暫停 {batch_pause:.2f} 秒")
                time.sleep(batch_pause)

    def process_url(self, url: str) -> Tuple[bool, Optional[Union[Dict, List[Dict]]]]:
        """處理 URL，判斷是播放清單還是單個影片。"""
        playlist_info = self.get_playlist_info(url, limit=1)
        if playlist_info and len(playlist_info['videos']) > 0:
            return True, None
        else:
            video_info = self.get_video_info(url)
            if video_info:
                return False, video_info
            return False, None

    def find_unfinished_playlists(self) -> List[Tuple[str, str]]:
        """查找未完成的播放清單下載任務"""
        unfinished = []
        if not os.path.exists(self.base_folder):
            return unfinished

        for folder_name in os.listdir(self.base_folder):
            folder_path = os.path.join(self.base_folder, folder_name)
            if not os.path.isdir(folder_path):
                continue

            json_path = os.path.join(folder_path, 'playlist.json')
            if os.path.exists(json_path):
                unfinished.append((folder_name, folder_path))

        return unfinished

    def continue_playlist_download(self, folder_path: str) -> None:
        """繼續下載未完成的播放清單"""
        json_path = os.path.join(folder_path, 'playlist.json')
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                videos = json.load(f)
        except Exception as e:
            print(f"載入播放清單 JSON 時發生錯誤：{e}")
            logging.error(f"載入播放清單 JSON 時發生錯誤：{e}")
            return

        download_log_path = os.path.join(folder_path, 'download_log.json')
        downloaded_videos = self.load_download_log(download_log_path)

        downloaded_count = len(downloaded_videos)
        total_count = len(videos)

        print(f"播放清單共有 {total_count} 個影片，已下載 {downloaded_count} 個")

        start_index_input = input(f"從第幾個影片開始下載？（1-{total_count}，預設：{downloaded_count+1}）：")
        start_index = int(start_index_input) - 1 if start_index_input.isdigit() else downloaded_count
        start_index = max(0, min(start_index, total_count - 1))

        limit_input = input("本次下載多少個影片？（輸入數字，或按 Enter 不限制）：")
        limit = int(limit_input) if limit_input.isdigit() else None

        format_input = input(
            "請選擇下載格式：\n1. 最佳影片+音訊（預設）\n2. 僅音訊 (MP3)\n3. 1080p\n4. 720p\n選擇：")
        format = self.format_map.get(format_input, 'b[ext=mp4]')

        self.download_videos(
            videos,
            folder_path,
            limit,
            format,
            batch_size=10,
            delay_min=1.0,
            delay_max=5.0,
            start_index=start_index
        )

        print("\n本次下載已完成")
        logging.info("本次下載已完成")

    def run(self) -> None:
        """主執行流程。"""
        self.ensure_folder_exists(self.base_folder)
        if not self.download_ytdlp():
            return

        unfinished_playlists = self.find_unfinished_playlists()
        if unfinished_playlists:
            print("檢測到以下未完成的播放清單下載：")
            for i, (playlist_title, folder_path) in enumerate(unfinished_playlists):
                print(f"{i+1}. {playlist_title}")

            choice = input("請選擇要繼續下載的播放清單編號（按 Enter 開始新的下載）：")
            if choice.isdigit() and 1 <= int(choice) <= len(unfinished_playlists):
                idx = int(choice) - 1
                self.continue_playlist_download(unfinished_playlists[idx][1])
                return

        url = input("請輸入影片或播放清單 URL：")
        logging.info(f"用戶輸入 URL：{url}")
        if not url:
            print("未提供 URL，程式結束")
            logging.error("未提供 URL")
            return

        is_playlist, video_info = self.process_url(url)

        if not is_playlist:
            if not video_info:
                print("無法取得影片資訊，程式結束")
                logging.error("無法取得影片資訊")
                return

            print(f"檢測到單個影片：{video_info['title']}")

            format_input = input(
                "請選擇下載格式：\n1. 最佳影片+音訊（預設）\n2. 僅音訊 (MP3)\n3. 1080p\n4. 720p\n選擇：")
            format = self.format_map.get(format_input, 'b[ext=mp4]')
            logging.info(f"選擇的下載格式：{format}")

            self.download_single_video(video_info, format)
            print("\n處理完成")
            logging.info("單個影片處理完成")
            return

        limit_input = input("是否限制下載數量？（輸入數字，或按 Enter 不限制）：")
        limit = int(limit_input) if limit_input.isdigit() else None
        logging.info(f"下載數量限制：{limit}")

        format_input = input(
            "請選擇下載格式：\n1. 最佳影片+音訊（預設）\n2. 僅音訊 (MP3)\n3. 1080p\n4. 720p\n選擇：")
        format = self.format_map.get(format_input, 'b[ext=mp4]')
        logging.info(f"選擇的下載格式：{format}")

        playlist_info = self.get_playlist_info(url, limit)
        if not playlist_info:
            print("無法取得播放清單資訊")
            logging.error("無法取得播放清單資訊")
            return

        folder_path = self.save_playlist_json(playlist_info)
        print(f"\n已建立播放清單 JSON 檔案於 {folder_path}")
        logging.info(f"已建立播放清單 JSON 檔案於 {folder_path}")

        download_now = input("是否立即下載這些影片？（y/n，預設：y）：").lower()
        logging.info(f"是否立即下載：{download_now}")
        if download_now != 'n':
            self.download_videos(
                playlist_info['videos'],
                folder_path,
                limit,
                format,
                batch_size=10,
                delay_min=1.0,
                delay_max=5.0
            )
            print("\n所有下載已完成")
            logging.info("所有下載已完成")
        else:
            print("\n已建立 JSON 檔案，未進行下載")
            logging.info("已建立 JSON 檔案，未進行下載")

        print("\n處理完成")
        logging.info("處理完成")


if __name__ == "__main__":
    downloader = VideoDownloader()
    downloader.run()


# python youtube.py

