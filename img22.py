import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from PIL import Image
from pathlib import Path
import platform

# --- 常量定义 ---
DEFAULT_OUTPUT_DIR_NAME = "out"  # 默认输出子目录名
SUPPORTED_FORMATS = ['.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp']  # 支持的图像扩展名

# --- Windows下的高DPI支持 ---
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except (ImportError, AttributeError):
    pass  # 在非Windows系统下忽略 DPI 相关设置

class MangaSplitterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("对半切切")  # 窗口标题
        self.root.geometry("800x550")     # 初始窗口大小
        self.root.minsize(500, 450)       # 最小窗口尺寸

        # --- 界面变量 ---
        self.src_dir = tk.StringVar()     # 源目录路径
        self.out_dir = tk.StringVar()     # 输出目录路径
        self.order = tk.IntVar(value=2)   # 命名顺序（1：从左往右，2：从右往左）
        self.quality = tk.IntVar(value=95)# 图像质量
        self.auto_skip = tk.BooleanVar(value=True)  # 是否跳过单页图
        self.status_text = tk.StringVar(value="就绪")  # 状态栏信息

        # --- 状态控制 ---
        self.is_running = False  # 是否正在处理
        self.stop_flag = False   # 停止标志

        # --- 构建 UI 界面 ---
        self.create_widgets()

        # --- 路径变更自动联动逻辑 ---
        self.src_dir.trace_add("write", self.sync_output_dir)  # 同步输出路径
        self.out_dir.trace_add("write", self.validate_inputs)  # 输出路径更新后验证按钮状态
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)  # 关闭事件绑定

        # --- 拖放支持初始化 ---
        self.setup_drag_and_drop()

    def create_widgets(self):
        # 主容器
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill='both', expand=True)

        # 路径选择区域
        path_frame = ttk.LabelFrame(main_frame, text="路径设置", padding="10")
        path_frame.pack(fill='x', pady=5)
        path_frame.columnconfigure(1, weight=1)

        # 图片文件夹输入
        ttk.Label(path_frame, text="📁 图片文件夹：").grid(row=0, column=0, sticky='w', pady=2)
        ttk.Entry(path_frame, textvariable=self.src_dir).grid(row=0, column=1, sticky='ew')
        ttk.Button(path_frame, text="浏览...", command=self.select_folder).grid(row=0, column=2, padx=(5, 0))

        # 输出文件夹输入
        ttk.Label(path_frame, text="📂 输出文件夹：").grid(row=1, column=0, sticky='w', pady=2)
        ttk.Entry(path_frame, textvariable=self.out_dir).grid(row=1, column=1, sticky='ew')
        ttk.Button(path_frame, text="浏览...", command=self.select_output_folder).grid(row=1, column=2, padx=(5, 0))

        # 处理选项区域
        opt_frame = ttk.LabelFrame(main_frame, text="处理选项", padding="10")
        opt_frame.pack(fill='x', pady=5)

        # 命名顺序选项
        order_frame = ttk.Frame(opt_frame)
        order_frame.pack(fill='x')
        ttk.Label(order_frame, text="🔢 命名顺序：").pack(side='left', anchor='w')
        ttk.Radiobutton(order_frame, text="从左往右 (左1, 右2)", variable=self.order, value=1).pack(side='left', padx=5)
        ttk.Radiobutton(order_frame, text="从右往左 (右1, 左2)", variable=self.order, value=2).pack(side='left', padx=5)

        # JPEG/WebP质量设置
        quality_frame = ttk.Frame(opt_frame)
        quality_frame.pack(fill='x', pady=5)
        ttk.Label(quality_frame, text="🖼️ JPEG/WebP 质量 (1-100)：").pack(side='left')
        ttk.Spinbox(quality_frame, from_=1, to=100, textvariable=self.quality, width=5).pack(side='left')

        # 跳过单页图开关
        ttk.Checkbutton(opt_frame, text="🧠 跳过单页图（宽度 < 高度的图片将原样复制）", variable=self.auto_skip).pack(anchor='w')

        # 控制按钮区域
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill='x', pady=10)

        # 开始按钮
        self.start_button = ttk.Button(control_frame, text="🚀 开始处理", command=self.start_thread, state='disabled')
        self.start_button.pack(side='left', padx=5, expand=True)

        # 停止按钮
        self.stop_button = ttk.Button(control_frame, text="🛑 停止处理", command=self.stop_processing, state='disabled')
        self.stop_button.pack(side='left', padx=5, expand=True)

        # 打开输出文件夹按钮
        self.open_out_button = ttk.Button(control_frame, text="📂 打开输出目录", command=self.open_output_dir, state='disabled')
        self.open_out_button.pack(side='left', padx=5, expand=True)

        # 状态栏与进度条
        ttk.Label(main_frame, textvariable=self.status_text, anchor='w').pack(fill='x')
        self.progress = ttk.Progressbar(main_frame, mode='determinate', maximum=100)
        self.progress.pack(fill='x', pady=5)

        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="处理日志", padding="5")
        log_frame.pack(fill='both', expand=True)
        self.log = ScrolledText(log_frame, height=10, relief='flat', wrap='word')
        self.log.pack(fill='both', expand=True)

        # 初始输入校验
        self.validate_inputs()

    def sync_output_dir(self, *args):
        # 当图片文件夹路径更改时，自动同步输出文件夹路径
        src_path = self.src_dir.get()
        if os.path.isdir(src_path):
            self.out_dir.set(os.path.join(src_path, DEFAULT_OUTPUT_DIR_NAME))
        self.validate_inputs()

    def setup_drag_and_drop(self):
        # 设置拖放逻辑（要求 root 为 TkinterDnD2.Tk 类型）
        try:
            from TkinterDnD2 import DND_FILES
            self.root.drop_target_register(DND_FILES)
            def drop_handler(event):
                path = self.root.tk.splitlist(event.data)[0]
                if os.path.isdir(path):
                    self.src_dir.set(path)
            self.root.dnd_bind('<<Drop>>', drop_handler)
            self.log_message("提示：拖入图片文件夹以开始")
        except (ImportError, tk.TclError):
            self.log_message("提示：拖放功能不可用。")

    def select_folder(self):
        folder = filedialog.askdirectory(initialdir=self.src_dir.get() or '.')
        if folder:
            self.src_dir.set(folder)

    def select_output_folder(self):
        folder = filedialog.askdirectory(initialdir=self.out_dir.get() or '.')
        if folder:
            self.out_dir.set(folder)

    def open_output_dir(self):
        # 跨平台打开文件夹
        out_path = self.out_dir.get()
        if os.path.isdir(out_path):
            try:
                if platform.system() == "Windows":
                    os.startfile(out_path)
                elif platform.system() == "Darwin":
                    os.system(f'open "{out_path}"')
                else:
                    os.system(f'xdg-open "{out_path}"')
            except Exception as e:
                messagebox.showerror("错误", f"无法打开文件夹：{e}")
        else:
            messagebox.showwarning("目录不存在", f"输出目录 '{out_path}' 不存在。")

    def validate_inputs(self, *args):
        # 根据输入路径合法性决定按钮启用状态
        is_valid_src = os.path.isdir(self.src_dir.get())
        is_valid_out = bool(self.out_dir.get())
        self.start_button.config(state='normal' if is_valid_src and is_valid_out and not self.is_running else 'disabled')
        self.open_out_button.config(state='normal' if os.path.isdir(self.out_dir.get()) else 'disabled')

    def start_thread(self):
        self.is_running = True
        self.stop_flag = False
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.open_out_button.config(state='disabled')
        self.progress['value'] = 0
        self.log.delete('1.0', 'end')
        self.update_status("正在初始化...")
        self.log_message("🚀 开始处理图片...")
        threading.Thread(target=self.process_images_thread, daemon=True).start()

    def stop_processing(self):
        # 请求终止后台处理线程
        if self.is_running:
            self.stop_flag = True
            self.update_status("正在请求停止...")
            self.log_message("🛑 正在停止处理...")
            self.stop_button.config(state='disabled')

    # 状态栏更新
    def update_status(self, text):
        self.root.after(0, lambda: self.status_text.set(text))

    # 日志输出
    def log_message(self, msg):
        self.root.after(0, lambda: (self.log.insert('end', msg + '\n'), self.log.see('end')))

    # 更新进度条
    def update_progress(self, value):
        self.root.after(0, lambda: self.progress.config(value=value))

    # 处理完成后的状态恢复
    def process_finished(self, final_message, success=True):
        self.is_running = False
        self.stop_flag = False
        self.update_status(final_message)
        final_log = f"🎉 {final_message}" if success else f"❌ {final_message}"
        self.log_message(final_log)
        self.root.after(0, self.validate_inputs)
        self.root.after(0, lambda: self.stop_button.config(state='disabled'))

    def process_images_thread(self):
        # 后台线程执行图像切割操作
        try:
            src = Path(self.src_dir.get())
            out = Path(self.out_dir.get())
            order = self.order.get()
            quality = self.quality.get()

            out.mkdir(parents=True, exist_ok=True)
            files = [f for f in os.listdir(src) if f.lower().endswith(tuple(SUPPORTED_FORMATS))]
            total_files = len(files)

            if not total_files:
                self.process_finished("完成（文件夹内没有支持的图片）", success=True)
                return

            for i, fname in enumerate(files):
                if self.stop_flag:
                    self.process_finished("处理已手动停止", success=False)
                    return

                self.update_status(f"处理中: {fname} ({i+1}/{total_files})")
                self.update_progress((i + 1) / total_files * 100)

                try:
                    img_path = src / fname
                    img = Image.open(img_path)

                    if img.mode in ['P', 'PA']:
                        img = img.convert('RGBA' if 'A' in img.mode else 'RGB')

                    w, h = img.size
                    name, ext = os.path.splitext(fname)
                    save_ext = ext.lower()
                    save_args = {}
                    if save_ext in ['.jpg', '.jpeg']:
                        save_args = {'quality': quality, 'subsampling': 0}
                    elif save_ext == '.webp':
                        save_args = {'quality': quality}

                    if self.auto_skip.get() and w < h:
                        img.save(out / fname, **save_args)
                        self.log_message(f"➡️ 跳过单页 (已复制): {fname}")
                        continue

                    left_crop = img.crop((0, 0, w//2, h))
                    right_crop = img.crop((w//2, 0, w, h))

                    if order == 1:
                        left_path = out / f"{name}_1{ext}"
                        right_path = out / f"{name}_2{ext}"
                    else:
                        right_path = out / f"{name}_1{ext}"
                        left_path = out / f"{name}_2{ext}"

                    left_crop.save(left_path, **save_args)
                    right_crop.save(right_path, **save_args)
                    self.log_message(f"✅ 已处理: {fname}")

                except Exception as e:
                    self.log_message(f"⚠️ 失败: {fname} -> {e}")

            if not self.stop_flag:
                self.process_finished("所有图片处理完成！", success=True)

        except Exception as e:
            self.process_finished(f"出现严重错误: {e}", success=False)

    def on_closing(self):
        # 关闭前提示确认
        if self.is_running:
            if not messagebox.askyesno("确认退出", "处理仍在进行中，确定要退出吗？"):
                return
        self.root.destroy()

# --- 主程序入口 ---
if __name__ == '__main__':
    DND_SUPPORT = False
    try:
        from TkinterDnD2 import Tk
        root = Tk()  # 拖放功能必须使用 TkinterDnD2.Tk 实例
        DND_SUPPORT = True
    except ImportError:
        import tkinter as tk
        root = tk.Tk()  # 若无 DnD 库，退回 tkinter.Tk（无拖放）

    app = MangaSplitterApp(root)
    root.mainloop()
