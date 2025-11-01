import os, re, json, requests, time
import flet as ft
from typing import Any, Optional, Dict, List
from pathlib import Path
from datetime import datetime

import init
init.Init()

from enum import IntEnum
class llv(IntEnum):
    DEBUG = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4   
    def __str__(self):
        return self.name
    
class PixivImageOrganizer:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = _("PixSense - Pixiv图片分类整理工具")
        self.page.window_width = 800
        self.page.window_height = 700
        self.page.scroll = "adaptive"
        
        self.log_output = ft.ListView(expand=True, spacing=10)  

        # 配置项
        self.config = {
            "source_dir": "",
            "target_dir": "",
            "filename_rule": "{id}",
            "folder_structure": "{user}/{title}",
            "overwrite_existing": False,
            "pixiv_cookie": "",
            "file_extensions": [".jpg", ".png", ".jpeg", ".gif"],
            "max_retries": 5,  # 最大重试次数
            "base_retry_delay": 3,  # 基础重试延迟(秒) - 改名为base_retry_delay更明确
            "max_retry_delay": 60,  # 最大重试延迟(秒)
            "enable_exponential_backoff": True,  # 是否启用指数退避
            "enable_jitter": True,  # 是否添加随机抖动
            "retry_on_429": True,  # 是否在429时自动重试
            "retry_on_timeout": True,  # 是否在超时时自动重试
            "thread_count": 5,
            "id_regex_pattern": r"(\d+)",  # 默认匹配连续数字
            "log_to_file": True,  # 新增：是否记录日志到文件
            "log_file_path": "pixsense.log",  # 新增：日志文件路径
            "log_level": "INFO",  # 新增：默认日志级别
            "clear_log_on_startup": True,  # 新增：启动时清空日志
            "tag_separator": ", "  # 标签连接符
        }
        
        # 加载保存的配置
        self.loadc()

        # UI元素
        self.setui()
        
        # 清空日志文件（如果启用）
        if self.config.get("log_to_file", False) and self.config.get("clear_log_on_startup", True):
            self.clear_log_file()
        
    def clear_log_file(self):
        """清空日志文件"""
        log_path = Path(self.config.get("log_file_path", "pixsense.log"))
        try:
            if log_path.exists():
                with open(log_path, "w", encoding="utf-8") as f:
                    f.write("")  # 清空文件内容
                self.log(_("已清空日志文件: %s") % log_path, llv.INFO)
        except Exception as e:
            self.log(_("清空日志文件失败: %s") % str(e), llv.ERROR)

    def setui(self):
        """设置用户界面"""
        # 源目录选择
        self.source_dir_field = ft.TextField(
            label=_("源图片目录"),
            value=self.config["source_dir"],
            expand=True
        )
        self.source_dir_picker = ft.FilePicker(on_result=lambda e: self.set_directory(e, self.source_dir_field))
        self.page.overlay.append(self.source_dir_picker)
        
        source_dir_row = ft.Row([
            self.source_dir_field,
            ft.ElevatedButton(
                _("选择目录"),
                on_click=lambda _: self.source_dir_picker.get_directory_path()
            )
        ])
        
        # 目标目录选择
        self.target_dir_field = ft.TextField(
            label=_("目标目录"),
            value=self.config["target_dir"],
            expand=True
        )
        self.target_dir_picker = ft.FilePicker(on_result=lambda e: self.set_directory(e, self.target_dir_field))
        self.page.overlay.append(self.target_dir_picker)
        
        target_dir_row = ft.Row([
            self.target_dir_field,
            ft.ElevatedButton(
                _("选择目录"),
                on_click=lambda _: self.target_dir_picker.get_directory_path()
            )
        ])
        
        # 文件名规则
        self.filename_rule_field = ft.TextField(
            label=_("文件名规则 (用于提取ID)"),
            value=self.config["filename_rule"],
            hint_text=_("如: {id} 或 {title}▪︎{id}｜{user}等"),
            expand=True
        )

        # 正则表达式输入框
        self.id_regex_field = ft.TextField(
            label=_("ID提取正则表达式"),
            value=self.config["id_regex_pattern"],
            hint_text=_("如: (\\d+) 或 id_(\\d+)"),
            expand=True
        )
        
        # 文件夹结构
        self.folder_structure_field = ft.TextField(
            label=_("文件夹结构"),
            value=self.config["folder_structure"],
            hint_text=_("如: {user}/{title} 或 {user_id}/{date}/{tags[0]}"),
            expand=True
        )
        
        # Pixiv Cookie
        self.pixiv_cookie_field = ft.TextField(
            label=_("Pixiv Cookie (PHPSESSID=...)"),
            value=self.config["pixiv_cookie"],
            password=True,
            can_reveal_password=True,
            expand=True
        )
        
        # 文件扩展名
        self.file_extensions_field = ft.TextField(
            label=_("支持的图片扩展名 (逗号分隔)"),
            value=", ".join(self.config["file_extensions"]),
            hint_text=_("如: .jpg, .png, .jpeg"),
            expand=True
        )
        
        # 其他选项
        self.overwrite_check = ft.Checkbox(
            label=_("覆盖已存在的文件"),
            value=self.config["overwrite_existing"]
        )
        
        # 重试配置行
        self.max_retries_field = ft.TextField(
            label=_("最大重试次数"),
            value=str(self.config["max_retries"]),
            input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9]", replacement_string=""),
            width=120
        )

        self.base_retry_delay_field = ft.TextField(
            label=_("基础延迟(秒)"),
            value=str(self.config["base_retry_delay"]),
            input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9]", replacement_string=""),
            width=120
        )

        self.max_retry_delay_field = ft.TextField(
            label=_("最大延迟(秒)"),
            value=str(self.config["max_retry_delay"]),
            input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9]", replacement_string=""),
            width=120
        )

        self.exponential_backoff_check = ft.Checkbox(
            label=_("指数退避"),
            value=self.config["enable_exponential_backoff"]
        )
        self.exponential_backoff_help = ft.Text(  # 添加工具提示
            value="(?)", 
            size=12, 
            color=ft.Colors.BLUE,
            tooltip=_("启用后，每次重试的等待时间会指数级增长（基础延迟×2^重试次数）")
        )

        self.jitter_check = ft.Checkbox(
            label=_("随机抖动"),
            value=self.config["enable_jitter"]
        )
        self.jitter_help = ft.Text(  # 添加工具提示
            value="(?)", 
            size=12, 
            color=ft.Colors.BLUE,
            tooltip=_("启用后，会在重试延迟上添加随机时间（0-1秒），避免多个请求同时重试")
        )

        self.retry_429_check = ft.Checkbox(
            label=_("429重试"),
            value=self.config["retry_on_429"]
        )
        self.retry_429_help = ft.Text(  # 添加工具提示
            value="(?)", 
            size=12, 
            color=ft.Colors.BLUE,
            tooltip=_("启用后，当收到429(请求过多)响应时会自动等待并重试")
        )

        self.retry_timeout_check = ft.Checkbox(
            label=_("超时重试"),
            value=self.config["retry_on_timeout"]
        )
        self.retry_timeout_help = ft.Text(  # 添加工具提示
            value="(?)", 
            size=12, 
            color=ft.Colors.BLUE,
            tooltip=_("启用后，当请求超时会自动重试")
        )

        self.thread_count_field = ft.TextField(
            label=_("线程数"),
            value=str(self.config["thread_count"]),
            input_filter=ft.InputFilter(allow=True, regex_string=r"[0-9]", replacement_string="")
        )
        
        # 日志输出
        self.log_output = ft.ListView(expand=True, spacing=10)
        
        # 操作按钮
        self.start_button = ft.ElevatedButton(
            _("开始整理"),
            on_click=self.org,
            icon=ft.Icons.PLAY_ARROW
        )
        
        self.savec_button = ft.ElevatedButton(
            _("保存配置"),
            on_click=self.savec,
            icon=ft.Icons.SAVE
        )
        
        self.log_to_file_check = ft.Checkbox(
            label=_("记录日志到文件"),
            value=self.config["log_to_file"]
        )
        
        self.log_file_path_field = ft.TextField(
            label=_("日志文件路径"),
            value=self.config["log_file_path"],
            expand=True
        )
        
        self.log_level_dropdown = ft.Dropdown(
            label=_("日志级别"),
            value=self.config["log_level"],
            options=[
                ft.dropdown.Option("DEBUG"),
                ft.dropdown.Option("INFO"),
                ft.dropdown.Option("WARNING"),
                ft.dropdown.Option("ERROR"),
                ft.dropdown.Option("CRITICAL"),
            ],
            expand=True
        )

        # 添加清空日志选项
        self.clear_log_check = ft.Checkbox(
            label=_("启动时清空日志"),
            value=self.config.get("clear_log_on_startup", True)
        )
        
        self.clear_log_button = ft.ElevatedButton(
            _("手动清空日志"),
            on_click=lambda _: self.clear_log_file(),
            icon=ft.Icons.DELETE
        )

        # 标签配置行
        self.tag_separator_field = ft.TextField(
            label=_("标签连接符"),
            value=self.config["tag_separator"],
            hint_text=_("如: , 或 -"),
            width=120
        )

        # 修改布局，添加日志相关控件
        self.page.add(
            ft.Column([
                ft.Text(_("PixSense - Pixiv图片分类整理工具"), size=24, weight="bold"),
                source_dir_row,
                target_dir_row,
                self.filename_rule_field,
                self.id_regex_field,
                self.folder_structure_field,
                ft.Row([
                    ft.Text(_("标签配置:"), width=100),
                    self.tag_separator_field
                ]),
                self.pixiv_cookie_field,
                self.file_extensions_field,
                ft.Row([  # 重试配置行
                    ft.Text(_("重试配置:"), width=100),
                    self.max_retries_field,
                    self.base_retry_delay_field,
                    self.max_retry_delay_field,
                    ft.Row([self.exponential_backoff_check, self.exponential_backoff_help], spacing=0),
                    ft.Row([self.jitter_check, self.jitter_help], spacing=0),
                    ft.Row([self.retry_429_check, self.retry_429_help], spacing=0),
                    ft.Row([self.retry_timeout_check, self.retry_timeout_help], spacing=0)
                ], 
                    wrap=False,  # 禁用自动换行
                    scroll=True  # 启用水平滚动
                ),
                ft.Row([  # 新增日志配置行
                    self.log_to_file_check,
                    self.log_file_path_field,
                    self.log_level_dropdown
                ]),
                self.overwrite_check,
                self.clear_log_check,
                ft.Row([
                    self.start_button,
                    self.savec_button,
                    self.clear_log_button
                ]),
                ft.Divider(),
                ft.Text(_("日志输出:"), size=18),
                ft.Container(
                    self.log_output,
                    border=ft.border.all(1),
                    padding=10,
                    expand=True
                )
            ], spacing=10, expand=True)
        )
    
    def set_directory(self, e: ft.FilePickerResultEvent, field: ft.TextField):
        """设置目录路径"""
        if e.path:
            field.value = e.path
            self.page.update()
    
    def savec(self, e):
        """保存配置"""
        self.config.update({
            "source_dir": self.source_dir_field.value,
            "target_dir": self.target_dir_field.value,
            "filename_rule": self.filename_rule_field.value,
            "folder_structure": self.folder_structure_field.value,
            "tag_separator": self.tag_separator_field.value,
            "id_regex_pattern": self.id_regex_field.value,
            "pixiv_cookie": self.pixiv_cookie_field.value,
            "file_extensions": [ext.strip() for ext in self.file_extensions_field.value.split(",")],
            "overwrite_existing": self.overwrite_check.value,
            "max_retries": int(self.max_retries_field.value),
            "base_retry_delay": int(self.base_retry_delay_field.value),
            "max_retry_delay": int(self.max_retry_delay_field.value),
            "enable_exponential_backoff": self.exponential_backoff_check.value,
            "enable_jitter": self.jitter_check.value,
            "retry_on_429": self.retry_429_check.value,
            "retry_on_timeout": self.retry_timeout_check.value,
            "thread_count": int(self.thread_count_field.value),
            "log_to_file": self.log_to_file_check.value,
            "log_file_path": self.log_file_path_field.value,
            "log_level": self.log_level_dropdown.value,
            "clear_log_on_startup": self.clear_log_check.value
        })
        
        try:
            with open("config.json", "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            self.log(_("配置已保存!"), llv.INFO)
        except Exception as e:
            self.log(_("保存配置失败: %s") % str(e), llv.ERROR)

    def log(self, message: str, level: llv = llv.INFO):
        """添加日志消息"""
        if not hasattr(self, 'log_output'):
            return
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{now}] [{level}] {message}"
        
        # 显示在UI中
        self.log_output.controls.append(ft.Text(log_entry))
        self.page.update()
        self.log_output.scroll_to(offset=-1, duration=100)
        
        # 记录到文件
        if self.config.get("log_to_file", False):
            try:
                current_level = llv[self.config.get("log_level", "INFO")]
                if level >= current_level:  # 比较枚举值
                    log_path = Path(self.config.get("log_file_path", "pixsense.log"))
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(log_entry + "\n")
            except Exception as e:
                self.log(_("无法写入日志文件: %s") % str(e), llv.ERROR)

    def loadc(self):
        """加载保存的配置"""
        try:
            if os.path.exists("config.json"):
                with open("config.json", "r", encoding="utf-8") as f:
                    loaded_config = json.load(f)
                    self.config.update(loaded_config)
        except Exception as e:
            self.log(_("加载配置失败: %s") % str(e), llv.ERROR)
    
    def org(self, e):
        """开始整理图片"""
        # 更新配置
        self.savec(None)
        
        # 验证配置
        if not self.config["source_dir"] or not os.path.isdir(self.config["source_dir"]):
            self.log(_("错误: 源目录无效或未设置"), llv.ERROR)
            return
            
        if not self.config["target_dir"]:
            self.log(_("错误: 目标目录未设置"), llv.ERROR)
            return
            
        if not self.config["pixiv_cookie"]:
            self.log(_("警告: 未设置Pixiv Cookie，可能无法获取详细信息"), llv.WARNING)
            
        # 创建目标目录
        os.makedirs(self.config["target_dir"], exist_ok=True)
        
        self.log(_("开始扫描源目录..."), llv.DEBUG)
        
        # 获取所有图片文件
        image_files = []
        for ext in self.config["file_extensions"]:
            image_files.extend(Path(self.config["source_dir"]).rglob(f"*{ext}"))
        
        self.log(_("找到 %d 个图片文件") % len(image_files))
        
        # 处理每个文件
        for file in image_files:
            try:
                self.process_file(file)
            except Exception as e:
                self.log(_("处理文件 %s 时出错: %s") % (file.name,str(e)), llv.ERROR)
        
        self.log(_("整理完成!"))
    
    def process_file(self, file_path: Path):
        """处理单个文件"""
        try:
            filename = file_path.stem
            self.log(_("处理文件: %s") % filename, llv.DEBUG)
            
            illust_id = self.extractId(filename)
            if not illust_id:
                self.log(_("无法从文件名 %s 中提取ID") % filename, llv.ERROR)
                return
                
            self.log(_("提取到ID: %s") % illust_id, llv.DEBUG)
            
            illust_info = self.getInfo(illust_id)
            if not illust_info:
                return
                
            # 验证illust_info数据结构
            if not isinstance(illust_info, dict):
                self.log(_("作品信息格式无效: %s") % type(illust_info), llv.ERROR)
                return
                
            # 安全访问嵌套数据
            title = str(illust_info.get("illustTitle", _("无标题")))
            user_name = str(illust_info.get("userName", _("未知用户")))
            
            # 处理tags数据
            tags_data = illust_info.get("tags", {})
            if not isinstance(tags_data, dict):
                tags_data = {}
                
            tags_list = tags_data.get("tags", [])
            if not isinstance(tags_list, list):
                tags_list = []
                
            # 构建目标路径
            target_path = self.buildPath({
                "illustId": illust_id,
                "illustTitle": title,
                "userName": user_name,
                "userId": str(illust_info.get("userId", "")),
                "createDate": illust_info.get("createDate", ""),
                "bookmarkCount": illust_info.get("bookmarkCount", 0),
                "tags": {"tags": tags_list}
            }, file_path.suffix)
            
            if not target_path:
                return
                    
            # 创建目录并复制/移动文件
            os.makedirs(target_path.parent, exist_ok=True)
            
            if target_path.exists() and not self.config["overwrite_existing"]:
                self.log(_("文件已存在，跳过: %s") % target_path)
                return
                
            self.log(_("文件路径：%s") % str(file_path), llv.DEBUG)
            self.log(_("目标路径：%s") % str(target_path), llv.DEBUG)
            # 复制文件
            import shutil
            shutil.copy2(file_path, target_path)
            self.log(_("文件已复制到: %s") % target_path)

        except Exception as e:
            self.log(_("处理文件 %s 时出错: %s") % (file_path.name,str(e)), llv.ERROR)
            import traceback
            self.log(_("错误详情:\n%s") % traceback.format_exc(), llv.DEBUG)
    
    def extractId(self, filename: str) -> Optional[str]:
        """从文件名中提取Pixiv ID"""
        # 尝试从文件名规则中提取
        rule = self.config["filename_rule"]
        
        # 如果规则直接包含{id_num}或{id}，尝试提取
        if ("{id_num}" in rule or "{id}" in rule):
            try:
                rule.replace("▪︎","[▪︎]")
                rule.replace("▪","[▪︎]")  # 这是两种不同的字符
                if "{id_num}" in rule:
                    pattern = rule.replace("{id_num}", r"(?P<id_num>\d+)")
                else:
                    pattern = rule.replace("{id}", r"(?P<id>\d+)(?:_p\d+)?")
                pattern = re.sub(r"{.*?}", r".*?", pattern)
                match = re.match(pattern, filename)
                if match:
                    return match.group("id")
            except re.error:
                self.log(_("正则表达式无效，尝试使用自定义正则表达式"), llv.WARNING)
                pass
        
        # 尝试使用自定义正则表达式
        if hasattr(self, "id_regex_pattern"):
            try:
                match = re.search(self.id_regex_pattern, filename)
                if match:
                    return match.group(1)
            except re.error:
                self.log(_("自定义正则表达式无效"), llv.WARNING)
                pass
        
        return None
    
    def getInfo(self, illust_id: str) -> Optional[Dict]:
        """通过Pixiv API获取作品信息"""
        if not self.config["pixiv_cookie"]:
            self.log(_("未设置Pixiv Cookie"), llv.WARNING)
            return None
            
        url = f"https://www.pixiv.net/ajax/illust/{illust_id}"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Cookie": self.config["pixiv_cookie"],
            "Referer": f"https://www.pixiv.net/artworks/{illust_id}"
        }
        
        response = None  # 初始化response变量
        last_status = None
        retries = 0
        
        while retries < self.config["max_retries"]:
            try:
                # 添加随机延迟避免请求过于频繁
                if retries > 0:
                    delay = self.calculate_retry_delay(retries)
                    self.log(_("等待 %.2f 秒后重试...") % delay, llv.DEBUG)
                    time.sleep(delay)
                
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=(15, 30)
                )
                last_status = response.status_code
                
                # 处理429状态码
                if response.status_code == 429:
                    retry_after = self.handle_rate_limit(response)
                    continue
                    
                # 处理其他错误状态码
                if response.status_code != 200:
                    self.handle_http_error(response.status_code)
                    if response.status_code in (403, 404):
                        break
                    retries += 1
                    continue
                    
                # 验证响应数据
                data = self.validate_response_data(response)
                if data is None:
                    retries += 1
                    continue
                    
                return data.get("body")
                
            except requests.exceptions.RequestException as e:
                self.log(_("API请求异常: %s: %s") % (type(e).__name__, str(e)), llv.ERROR)
                retries += 1
        
        # 最终失败处理
        self.log_final_failure(illust_id, last_status)
        return None

    def calculate_retry_delay(self, retries: int) -> float:
        """计算重试延迟时间"""
        delay = min(
            self.config["base_retry_delay"] * (2 ** (retries - 1)),
            self.config["max_retry_delay"]
        )
        if self.config["enable_jitter"]:
            import random
            delay += random.uniform(0, 1)
        return delay

    def handle_rate_limit(self, response) -> int:
        """处理速率限制"""
        retry_after = int(response.headers.get('Retry-After', self.config["max_retry_delay"]))
        self.log(
            _("请求过于频繁，Pixiv要求等待 %d 秒 (HTTP 429)" % retry_after),
            llv.WARNING
        )
        time.sleep(retry_after)
        return retry_after

    def handle_http_error(self, status_code: int):
        """处理HTTP错误"""
        if status_code >= 500:
            self.log(_("服务器错误: HTTP %d" % status_code), llv.ERROR)
        else:
            self.log(_("客户端错误: HTTP %d" % status_code), llv.WARNING)

    def validate_response_data(self, response) -> Optional[Dict]:
        """验证响应数据格式"""
        try:
            data = response.json()
            if not isinstance(data, dict):
                self.log(_("API返回数据格式无效"), llv.ERROR)
                return None
            if data.get("error"):
                self.log(_("API错误: %s") % data.get('message', _('未知错误')), llv.ERROR)
                return None
            return data
        except ValueError:
            self.log(_("API返回无效的JSON数据"), llv.ERROR)
            return None

    def log_final_failure(self, illust_id: str, last_status: Optional[int]):
        """记录最终失败日志"""
        status_msg = str(last_status) if last_status else _("无响应")
        self.log(
            _("获取作品 %s 信息失败 (最终状态: %s)" % (illust_id, status_msg)),
            llv.ERROR
        )
    
    def buildPath(self, illust_info: Dict, file_ext: str) -> Optional[Path]:
        """构建目标路径"""
        if not illust_info or not isinstance(illust_info, dict):
            self.log(_("无效的作品信息数据"), llv.ERROR)
            return None
            
        # 处理标签数据
        processed_tags = self.process_tags_data(illust_info.get("tags", {}))
        tag_sep = self.config.get("tag_separator", ", ")

        # 准备替换变量 - 显式添加所有已知字段
        variables = {
            "id": str(illust_info.get("illustId", "")),
            "title": self.sanitize(illust_info.get("illustTitle", "无标题")),
            "user": self.sanitize(illust_info.get("userName", "未知用户")),
            "user_id": str(illust_info.get("userId", "")),
            "date": datetime.strptime(illust_info.get("createDate", ""), "%Y-%m-%dT%H:%M:%S%z").strftime("%Y%m%d") 
                if illust_info.get("createDate") else "",
            "bmk_1000": str(illust_info.get("bookmarkCount", 0) // 1000),
            "sl": str(illust_info.get("sl", "")),
            "illustComment": str(illust_info.get("illustComment", "")),  # 显式添加
            "titleCaptionTranslation": json.dumps(illust_info.get("titleCaptionTranslation", {}), ensure_ascii=False),  # 处理嵌套对象
            "tags": processed_tags,
            "tags_str": tag_sep.join(tag.get("tag", "") for tag in processed_tags),
            "tags_transl": tag_sep.join(
                f"{tag.get('tag', '')}({tag.get('translation', {}).get('en', '')})" 
                if tag.get("translation", {}).get("en") 
                else tag.get("tag", "") 
                for tag in processed_tags
            ),
            "tags_transl_only": tag_sep.join(
                tag.get("translation", {}).get("en", "") or tag.get("tag", "") 
                for tag in processed_tags
            )
        }
        
        # 深度遍历illust_info添加所有其他字段
        def add_nested_fields(source, prefix=""):
            for key, value in source.items():
                full_key = f"{prefix}_{key}" if prefix else key
                if isinstance(value, dict):
                    add_nested_fields(value, full_key)
                elif key not in variables:  # 不覆盖已处理的字段
                    if isinstance(value, (str, int, float, bool)):
                        variables[full_key] = str(value)
                    elif isinstance(value, list):
                        variables[full_key] = json.dumps(value, ensure_ascii=False)
                    elif value is None:
                        variables[full_key] = ""
                    else:
                        variables[full_key] = str(value)
        
        add_nested_fields(illust_info)
        
        # 检查缺失变量
        required_vars = set(re.findall(r"{(\w+)}", self.config["folder_structure"]))
        missing_vars = required_vars - set(variables.keys())
        if missing_vars:
            self.log(_("警告: 配置中要求的变量 %s 不存在于API返回数据中" % missing_vars), llv.WARNING)
            for var in missing_vars:
                variables[var] = ""
        
        self.log(variables,llv.DEBUG)
        try:
            # 创建文件夹路径
            folder_path = self.config["folder_structure"].format(**variables)
            # 清理路径中的非法字符
            self.sanitize(folder_path)
            # 构建完整路径
            filename = f"{variables['id']}{file_ext}"
            full_path = Path(self.config["target_dir"]) / folder_path / filename

            return full_path
            
        except Exception as e:
            self.log(_("构建路径失败: %s") % str(e), llv.ERROR)
            # 回退到简单路径
            return Path(self.config["target_dir"]) / str(variables["user_id"]) / f"{variables['id']}{file_ext}"
    
    def process_tags_data(self, tags_data: Any) -> List[Dict]:
        """安全处理标签数据"""
        if not isinstance(tags_data, dict):
            return []
        
        tags_list = tags_data.get("tags", [])
        if not isinstance(tags_list, list):
            return []
        
        # 确保每个标签项是字典且包含必要字段
        processed_tags = []
        for tag in tags_list:
            if isinstance(tag, dict):
                processed_tags.append({
                    "tag": str(tag.get("tag", "")),
                    "translation": tag.get("translation", {})
                })
        return processed_tags

    def get_translated_tags_only(self, tags_data: Any) -> str:
        """获取仅翻译的标签"""
        tags = self.process_tags_data(tags_data)
        trans_sep = self.config.get("tag_translation_separator", " ")
        return trans_sep.join(
            tag.get("translation", {}).get("en", "")
            for tag in tags
            if tag.get("translation", {}).get("en", "")
        )
    
    def sanitize(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        # Windows文件名非法字符: \ / : * ? " < > |
        illegal_chars = r'\/:*?"<>|'
        for char in illegal_chars:
            filename = filename.replace(char, "_")
        return filename.strip()

def main(page: ft.Page):
    PixivImageOrganizer(page)

if __name__ == "__main__":
    ft.app(target=main)