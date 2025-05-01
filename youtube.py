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
    encoding='utf-8'  # 確保日誌文件使用 UTF-8 編碼
)


class YouTubeDownloader:
    def __init__(self, base_folder: str = "./youtube_downloads"):
        self.base_folder = base_folder
        self.ytdlp_path = './yt-dlp.exe'  # Windows 版本
 
        # 更精確的 1080p 優先設定
        # 更精確的最高畫質格式選擇
        self.format_map = {
            '1': 'bestvideo+bestaudio/best',  # 絕對最高畫質（不限制格式）
            '2': 'ba[ext=m4a]',  # 僅音訊
            '3': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',  # 1080p
            '4': 'bestvideo[height<=720]+bestaudio/best[height<=720]'  # 720p
        }


        # 支持的編碼列表，用於嘗試解碼 subprocess 輸出
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
        # 確保 filename 是字串
        if not isinstance(filename, str):
            filename = str(filename)
        # 移除無效字符
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        # 去除前後空白並限制長度
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

    def is_playlist_url(self, url: str) -> bool:
        """檢查 URL 是否為 YouTube 播放清單 URL。"""
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        is_playlist = 'list' in query_params
        logging.info(f"檢查 URL：{url}，是否為播放清單：{is_playlist}")
        return is_playlist

    def is_youtube_url(self, url: str) -> bool:
        """檢查是否為有效的 YouTube URL。"""
        parsed = urlparse(url)
        return parsed.netloc in ('youtube.com', 'www.youtube.com', 'youtu.be')

    def run_subprocess_with_encoding(self, cmd: List[str], description: str = "") -> Optional[subprocess.CompletedProcess]:
        """執行 subprocess 命令並處理編碼問題。"""
        print(f"執行命令：{' '.join(cmd)}")
        logging.info(f"執行命令：{' '.join(cmd)}")

        # 直接使用 bytes 模式，手動處理解碼
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=False
            )

            # 嘗試不同的編碼解碼輸出
            stdout_text = None
            stderr_text = None

            for encoding in self.encodings_to_try:
                try:
                    if stdout_text is None:
                        stdout_text = result.stdout.decode(encoding)
                    if stderr_text is None:
                        stderr_text = result.stderr.decode(encoding)

                    # 如果兩者都成功解碼，跳出循環
                    if stdout_text and stderr_text:
                        print(f"成功使用 {encoding} 編碼解析輸出")
                        logging.info(f"成功使用 {encoding} 編碼解析輸出")
                        break
                except UnicodeDecodeError:
                    # 如果解碼失敗，繼續嘗試下一個編碼
                    continue

            # 如果仍然無法解碼，使用替換模式
            if stdout_text is None:
                stdout_text = result.stdout.decode('utf-8', errors='replace')
            if stderr_text is None:
                stderr_text = result.stderr.decode('utf-8', errors='replace')

            # 創建一個新的 CompletedProcess 對象，但使用解碼後的文本
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
            # 使用更穩定的參數組合
            cmd = [
                self.ytdlp_path,
                video_url,
                '--print', 'id',
                '--print', 'title',
                '--no-warnings',
                '--no-playlist',  # 確保不會處理為播放清單
                '--ignore-errors'  # 忽略部分錯誤以獲取更多資訊
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

                # 檢查是否為會員專屬內容
                if "This video is available to this channel's members" in result.stderr:
                    print("\n===== 會員專屬內容 =====")
                    print("此視頻是頻道會員專屬內容，需要成為會員才能訪問。")
                    print("===========================\n")
                    logging.error("視頻為會員專屬內容，無法下載")

                    # 從錯誤信息中提取視頻 ID
                    video_id = None
                    for line in result.stderr.split("\n"):
                        if "ERROR: [youtube]" in line:
                            parts = line.split(":")
                            if len(parts) > 1:
                                video_id = parts[1].strip().split(" ")[
                                    0].strip()
                                break

                    if video_id:
                        return {
                            "link": video_url,
                            "title": "會員專屬視頻",
                            "id": video_id,
                            "member_only": True
                        }

                # 嘗試使用更詳細的輸出模式獲取更多調試信息
                debug_cmd = [self.ytdlp_path, video_url, '-v', '--no-playlist']
                debug_result = self.run_subprocess_with_encoding(
                    debug_cmd, "調試影片資訊")

                if debug_result:
                    print(f"調試信息：{debug_result.stderr}")
                    logging.error(f"調試信息：{debug_result.stderr}")

                return None

            # 處理輸出
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
                print(f"YouTube API 返回 NA 值，可能是影片不可用或地區限制")
                logging.error(f"YouTube API 返回 NA 值，可能是影片不可用或地區限制")
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

        # 驗證是否為播放清單 URL
        if not self.is_playlist_url(playlist_url):
            print("錯誤：輸入的 URL 不是有效的 YouTube 播放清單 URL（缺少 list= 參數）")
            print("播放清單 URL 應類似：https://www.youtube.com/playlist?list=PL...")
            logging.error(f"無效的播放清單 URL：{playlist_url}")
            return None

        # 首先獲取播放清單標題
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
                logging.error(
                    f"取得播放清單標題失敗：{result.stderr if result else 'N/A'}")
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

        # 嘗試獲取播放清單中的影片 ID 和標題
        try:
            # 使用 --flat-playlist 只獲取基本信息，不嘗試下載
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

            videos_result = self.run_subprocess_with_encoding(
                videos_cmd, "取得播放清單影片")

            if videos_result is None:
                print("執行命令失敗，無法獲取結果")
                logging.error("執行命令失敗，無法獲取結果")
                return None

            # 檢查是否有會員限制錯誤
            is_member_only = "This video is available to this channel's members" in videos_result.stderr

            # 從錯誤信息中提取視頻 ID
            member_video_ids = []
            if is_member_only:
                stderr_lines = videos_result.stderr.split('\n')
                for line in stderr_lines:
                    if "ERROR: [youtube]" in line:
                        parts = line.split(":")
                        if len(parts) > 1:
                            video_id = parts[1].strip().split(":")[0].strip()
                            member_video_ids.append(video_id)

                if member_video_ids:
                    print(f"\n===== 會員專屬內容 =====")
                    print(f"此播放清單包含 {len(member_video_ids)} 個頻道會員專屬視頻")
                    print(f"這些視頻需要「進階應考專區(不再更新)」或更高級別的會員資格才能訪問")
                    print(f"已提取視頻 ID 並保存到 JSON 文件中，但無法下載視頻內容")
                    print(f"===========================\n")
                    logging.warning(f"播放清單包含 {len(member_video_ids)} 個會員專屬視頻")

            # 處理正常輸出
            videos = []
            stdout_content = videos_result.stdout if videos_result.stdout else ""
            lines = stdout_content.strip().split('\n')

            # 每兩行為一組（ID 和標題）
            for i in range(0, len(lines), 2):
                if i + 1 < len(lines):
                    video_id = lines[i].strip()
                    video_title = lines[i + 1].strip()
                    videos.append({
                        "link": f"https://www.youtube.com/watch?v={video_id}",
                        "title": video_title
                    })

            # 如果沒有從標準輸出獲取到視頻，但有會員專屬視頻 ID
            if not videos and member_video_ids:
                videos = [
                    {
                        "link": f"https://www.youtube.com/watch?v={vid}",
                        "title": f"會員專屬視頻 {i+1}",
                        "member_only": True
                    }
                    for i, vid in enumerate(member_video_ids)
                ]

                playlist_info = {
                    "title": playlist_title,
                    "videos": videos,
                    "member_only": True
                }
                return playlist_info

            if not videos:
                print("播放清單中沒有可訪問的影片")
                logging.error("播放清單中沒有可訪問的影片")
                return None

            playlist_info = {
                "title": playlist_title,
                "videos": videos,
                "member_only": is_member_only
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
        member_only = playlist_info.get('member_only', False)

        if member_only:
            print(f"已儲存 JSON 檔案，包含 {video_count} 個會員專屬影片：{json_path}")
            logging.info(f"已儲存 JSON 檔案（會員專屬內容）：{json_path}")
        else:
            print(f"已儲存 JSON 檔案，包含 {video_count} 個影片：{json_path}")
            logging.info(f"已儲存 JSON 檔案：{json_path}")

        return folder_path

    def download_single_video(self, video_info: Dict, format: str = 'b[ext=mp4]') -> None:
        """下載單個影片。"""
        if not video_info:
            print("沒有影片資訊可用於下載")
            logging.error("沒有影片資訊可用於下載")
            return

        # 檢查是否為會員專屬內容
        if video_info.get('member_only', False):
            print("\n===== 會員專屬內容 =====")
            print("此視頻是頻道會員專屬內容，需要成為會員才能訪問。")
            print("無法下載視頻內容。")
            print("===========================\n")
            logging.warning("嘗試下載會員專屬內容，已跳過")
            return

        # 建立資料夾
        folder_path = os.path.join(self.base_folder, "單個影片")
        self.ensure_folder_exists(folder_path)

        # 安全的檔案名稱處理
        safe_title = self.sanitize_filename(video_info['title'])
        ext = 'mp4' if 'mp4' in format else 'm4a' if 'm4a' in format else 'mp4'
        output_file = self.get_unique_filename(folder_path, safe_title, ext)

        print(f"正在下載影片：{video_info['title']}")
        logging.info(f"正在下載影片：{video_info['title']}")

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
                print(f'✓ 下載成功：{video_info["title"]}')
                print(f'儲存位置：{output_file}')
                logging.info(f'下載成功：{video_info["title"]}，儲存位置：{output_file}')
            else:
                stderr_msg = result.stderr if result and result.stderr else "未知錯誤"

                # 檢查是否為會員專屬內容錯誤
                if result and "This video is available to this channel's members" in result.stderr:
                    print(f'✗ 下載失敗：{video_info["title"]} - 此視頻為會員專屬內容')
                    logging.error(f'下載失敗：{video_info["title"]} - 會員專屬內容')
                else:
                    print(f'✗ 下載失敗：{video_info["title"]}\n錯誤：{stderr_msg}')
                    logging.error(
                        f'下載失敗：{video_info["title"]}，錯誤：{stderr_msg}')

        except Exception as e:
            print(f"下載影片時發生錯誤：{e}")
            logging.error(f"下載影片時發生錯誤：{e}")

    def download_videos(
        self,
        videos: List[Dict],
        folder_path: str,
        limit: Optional[int] = None,
        format: str = 'b[ext=mp4]',
        batch_size: int = 10,
        delay_min: float = 1.0,
        delay_max: float = 5.0
    ) -> None:
        """分批下載影片，使用影片標題作為檔案名稱。"""
        if not videos:
            print("沒有影片可下載")
            logging.info("沒有影片可下載")
            return

        # 檢查是否所有視頻都是會員專屬內容
        all_member_only = all(video.get('member_only', False)
                              for video in videos)

        if all_member_only:
            print("\n===== 會員專屬內容 =====")
            print("此播放清單中的所有視頻都是頻道會員專屬內容")
            print("這些視頻需要「進階應考專區(不再更新)」或更高級別的會員資格才能訪問")
            print("無法下載任何視頻內容")
            print("===========================\n")
            logging.warning("播放清單全部為會員專屬內容，跳過下載")
            return

        # 過濾出非會員專屬內容
        downloadable_videos = [
            v for v in videos if not v.get('member_only', False)]

        videos_to_download = downloadable_videos[:limit] if limit and limit < len(
            downloadable_videos) else downloadable_videos
        print(f"將下載 {len(videos_to_download)}/{len(videos)} 個影片")
        if len(videos_to_download) < len(videos):
            print(f"注意：有 {len(videos) - len(videos_to_download)} 個視頻因為會員限制無法下載")
        logging.info(f"將下載 {len(videos_to_download)}/{len(videos)} 個影片")

        for batch_start in range(0, len(videos_to_download), batch_size):
            batch = videos_to_download[batch_start:batch_start + batch_size]
            print(f"\n處理批次 {batch_start//batch_size + 1} "
                  f"({batch_start + 1}-{min(batch_start + batch_size, len(videos_to_download))})")
            logging.info(
                f"處理批次 {batch_start//batch_size + 1} ({batch_start + 1}-{min(batch_start + batch_size, len(videos_to_download))})")

            for i, video in enumerate(tqdm(batch, desc="批次進度")):
                try:
                    # 跳過會員專屬內容
                    if video.get('member_only', False):
                        print(f"\n跳過會員專屬視頻：{video.get('title', '未知標題')}")
                        logging.info(f"跳過會員專屬視頻：{video.get('title', '未知標題')}")
                        continue

                    link = video.get('link')
                    raw_title = video.get('title', '未知標題')
                    if not link:
                        print(f"錯誤：第 {batch_start + i + 1} 項缺少連結")
                        logging.error(f"第 {batch_start + i + 1} 項缺少連結")
                        continue

                    print(
                        f"\n正在下載 ({batch_start + i + 1}/{len(videos_to_download)})：{raw_title}")
                    logging.info(
                        f"正在下載 ({batch_start + i + 1}/{len(videos_to_download)})：{raw_title}")

                    # 安全的檔案名稱處理
                    safe_title = self.sanitize_filename(raw_title)
                    ext = 'mp4' if 'mp4' in format else 'm4a' if 'm4a' in format else 'mp4'
                    output_file = self.get_unique_filename(
                        folder_path, safe_title, ext)

                    cmd = [
                        self.ytdlp_path,
                        link,
                        '-f', format,
                        '-o', output_file,
                        '--progress',
                        '--no-overwrites'
                    ]

                    result = self.run_subprocess_with_encoding(
                        cmd, f"下載影片 {batch_start + i + 1}/{len(videos_to_download)}")

                    if result and result.returncode == 0:
                        print(f'✓ 下載成功：{raw_title}')
                        logging.info(f'下載成功：{raw_title}')
                    else:
                        stderr_msg = result.stderr if result and result.stderr else "未知錯誤"

                        # 檢查是否為會員專屬內容錯誤
                        if result and "This video is available to this channel's members" in result.stderr:
                            print(f'✗ 下載失敗：{raw_title} - 此視頻為會員專屬內容')
                            logging.error(f'下載失敗：{raw_title} - 會員專屬內容')
                        else:
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
        if not self.is_youtube_url(url):
            print("錯誤：輸入的不是有效的 YouTube URL")
            logging.error(f"無效的 YouTube URL：{url}")
            return False, None

        if self.is_playlist_url(url):
            return True, None  # 是播放清單，但尚未獲取資訊
        else:
            # 單個影片
            video_info = self.get_video_info(url)
            if video_info:
                return False, video_info
            return False, None

    def run(self) -> None:
        """主執行流程。"""
        self.ensure_folder_exists(self.base_folder)
        if not self.download_ytdlp():
            return

        url = input("請輸入 YouTube 影片或播放清單 URL：")
        logging.info(f"用戶輸入 URL：{url}")
        if not url:
            print("未提供 URL，程式結束")
            logging.error("未提供 URL")
            return

        is_playlist, video_info = self.process_url(url)

        # 如果是單個影片
        if not is_playlist:
            if not video_info:
                print("無法取得影片資訊，程式結束")
                logging.error("無法取得影片資訊")
                return

            print(f"檢測到單個影片：{video_info['title']}")

            # 檢查是否為會員專屬內容
            if video_info.get('member_only', False):
                print("\n===== 會員專屬內容 =====")
                print("此視頻是頻道會員專屬內容，需要成為會員才能訪問。")
                print("無法下載視頻內容。")
                print("===========================\n")
                logging.warning("視頻為會員專屬內容，無法下載")
                print("\n處理完成")
                logging.info("處理完成")
                return

            format_input = input(
                "請選擇下載格式：\n1. 最佳影片+音訊（預設）\n2. 僅音訊 (MP3)\n3. 1080p\n4. 720p\n選擇：")
            format = self.format_map.get(format_input, 'b[ext=mp4]')
            logging.info(f"選擇的下載格式：{format}")

            self.download_single_video(video_info, format)
            print("\n處理完成")
            logging.info("單個影片處理完成")
            return

        # 如果是播放清單
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

        # 檢查是否為全部會員專屬內容
        all_member_only = all(video.get('member_only', False)
                              for video in playlist_info['videos'])

        if all_member_only:
            print("\n此播放清單中的所有視頻都是頻道會員專屬內容")
            print("無法下載任何視頻內容")
            logging.warning("播放清單全部為會員專屬內容，跳過下載")
            print("\n處理完成")
            logging.info("處理完成")
            return

        # 檢查是否有部分會員專屬內容
        has_member_only = any(video.get('member_only', False)
                              for video in playlist_info['videos'])
        if has_member_only:
            member_only_count = sum(
                1 for video in playlist_info['videos'] if video.get('member_only', False))
            print(f"\n注意：此播放清單中有 {member_only_count} 個視頻是會員專屬內容")
            print("這些視頻將被跳過下載")
            logging.warning(f"播放清單中有 {member_only_count} 個會員專屬視頻")

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
    downloader = YouTubeDownloader()
    downloader.run()



# python youtube.py
