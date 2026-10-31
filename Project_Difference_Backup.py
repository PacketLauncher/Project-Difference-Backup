import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import queue
import shutil
import stat
import tempfile
import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import sys

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

APP_TITLE = 'Project Difference Backup'


def same_or_inside(path, root):
    try:
        return os.path.commonpath((os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(root)))) == os.path.normcase(os.path.realpath(root))
    except ValueError:
        return False


def set_windows_times(source, destination):
    if os.name != 'nt':
        return
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    CreateFileW = kernel32.CreateFileW
    CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    CreateFileW.restype = wintypes.HANDLE
    GetFileTime = kernel32.GetFileTime
    GetFileTime.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
    SetFileTime = kernel32.SetFileTime
    SetFileTime.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    ACCESS_READ = 0x80
    ACCESS_WRITE = 0x100
    SHARE = 0x1 | 0x2 | 0x4
    FLAGS = 0x02000000 if os.path.isdir(source) else 0x80
    invalid = ctypes.c_void_p(-1).value
    src = CreateFileW(str(source), ACCESS_READ, SHARE, None, 3, FLAGS, None)
    if src == invalid:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        created, accessed, modified = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
        if not GetFileTime(src, ctypes.byref(created), ctypes.byref(accessed), ctypes.byref(modified)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        CloseHandle(src)
    dst = CreateFileW(str(destination), ACCESS_WRITE, SHARE, None, 3, FLAGS, None)
    if dst == invalid:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not SetFileTime(dst, ctypes.byref(created), ctypes.byref(accessed), ctypes.byref(modified)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        CloseHandle(dst)


def scan(root):
    found = {}
    directories = {Path('.')}
    for current, subdirs, filenames in os.walk(root, followlinks=False):
        relative_dir = Path(current).relative_to(root)
        directories.add(relative_dir)
        for name in subdirs:
            p = Path(current) / name
            if p.is_symlink():
                raise ValueError(f'Symbolic-link directory is not supported: {p}')
        for name in filenames:
            p = Path(current) / name
            if p.is_symlink():
                raise ValueError(f'Symbolic-link file is not supported: {p}')
            found[str((relative_dir / name)).casefold()] = relative_dir / name
    return found, directories


def copy_selected(source_root, output_root, relative_paths, directories):
    needed = {Path('.')}
    for rel in relative_paths:
        parent = rel.parent
        while parent != Path('.'):
            needed.add(parent)
            parent = parent.parent
    for rel in sorted(needed, key=lambda p: (len(p.parts), str(p))):
        (output_root / rel).mkdir(parents=True, exist_ok=True)
    for rel in relative_paths:
        src, dst = source_root / rel, output_root / rel
        shutil.copy2(src, dst)
        set_windows_times(src, dst)
    for rel in sorted(needed, key=lambda p: (-len(p.parts), str(p))):
        src = source_root / rel
        dst = output_root / rel
        shutil.copystat(src, dst)
        set_windows_times(src, dst)


def files_have_same_content(first, second):
    """Compare actual bytes, without relying on timestamps or filecmp caching."""
    if first.stat().st_size != second.stat().st_size:
        return False
    with first.open('rb') as left, second.open('rb') as right:
        while True:
            left_chunk = left.read(1024 * 1024)
            right_chunk = right.read(1024 * 1024)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


def run_comparison(original, modified, save, report):
    original_files, original_dirs = scan(original)
    modified_files, modified_dirs = scan(modified)
    original_selected, modified_selected, rows = [], [], []
    for key in sorted(original_files.keys()):
        a = original_files.get(key)
        b = modified_files.get(key)
        if a is not None and b is not None:
            if files_have_same_content(original / a, modified / b):
                continue
        if a is not None:
            original_selected.append(a)
        if b is not None:
            modified_selected.append(b)
        rows.append((str(original / a) if a else '', str(modified / b) if b else ''))
    report(f'Found {len(rows)} differing file paths. Preparing new backup...')
    save.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.project_diff_', dir=save))
    try:
        copy_selected(original, staging / 'Original', original_selected, original_dirs)
        copy_selected(modified, staging / 'Modified', modified_selected, modified_dirs)
        with (staging / 'Results.txt').open('w', encoding='utf-8-sig', newline='') as f:
            f.write('Original path\tModified path\r\n')
            for left, right in rows:
                f.write(f'{left}\t{right}\r\n')
        # Move old results aside, then publish the complete new comparison.
        # Roll back the previous comparison if publishing fails.
        retired = staging / '_previous'
        retired.mkdir()
        names = ('Original', 'Modified', 'Results.txt')
        moved_old, moved_new = [], []
        try:
            for name in names:
                existing = save / name
                if existing.exists() or existing.is_symlink():
                    if existing.is_symlink():
                        raise ValueError(f'Output path is a symbolic link: {existing}')
                    os.replace(existing, retired / name)
                    moved_old.append(name)
            for name in names:
                os.replace(staging / name, save / name)
                moved_new.append(name)
        except Exception:
            for name in reversed(moved_new):
                published = save / name
                if published.is_dir():
                    shutil.rmtree(published)
                elif published.exists():
                    published.unlink()
            for name in reversed(moved_old):
                os.replace(retired / name, save / name)
            raise
        # Cleanup failures after successful publication should not roll back new results.
        try:
            shutil.rmtree(retired)
        except OSError as exc:
            report(f'Warning: old comparison cleanup failed: {exc}')
        report(f'Completed: {len(rows)} differences. Results.txt updated.')
    finally:
        try:
            shutil.rmtree(staging)
        except OSError:
            pass


class Application(TkinterDnD.Tk if TkinterDnD else tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)

        if getattr(sys, 'frozen', False):
            self.icon_path = os.path.join(sys._MEIPASS, 'Icon.ico')
        else:
            self.icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Icon.ico')

        if os.path.isfile(self.icon_path):
            self.iconbitmap(self.icon_path)

        self.geometry('670x350')
        self.minsize(670, 350)
        self.vars = [tk.StringVar() for _ in range(3)]
        self.events = queue.Queue()
        self.current_save = None
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill='both', expand=True)
        for index, label in enumerate(('Original path:', 'Modified path:', 'Save results to:')):
            ttk.Label(frame, text=label).grid(row=index * 2, column=0, sticky='w', pady=(0, 3))
            entry = ttk.Entry(frame, textvariable=self.vars[index])
            entry.grid(row=index * 2 + 1, column=0, sticky='ew', pady=(0, 10))
            if DND_FILES is not None:
                entry.drop_target_register(DND_FILES)
                entry.dnd_bind('<<Drop>>', lambda event, i=index: self.on_drop(event, i))
            ttk.Button(frame, text='Browse...', command=lambda i=index: self.browse(i)).grid(row=index * 2 + 1, column=1, padx=(10, 0), sticky='ew', pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        self.go = ttk.Button(frame, text='Compare and Back Up Differences', command=self.start)
        self.go.grid(row=6, column=0, columnspan=2, sticky='ew', pady=(4, 10))
        self.about_button = ttk.Button(frame, text='About', command=self.show_about)
        self.about_button.grid(row=9, column=1, sticky='e', pady=(8, 0))
        self.status = tk.StringVar(value='Ready')
        ttk.Label(frame, textvariable=self.status).grid(row=7, column=0, columnspan=2, sticky='w')
        self.log = tk.Text(frame, height=5, state='disabled', wrap='word')
        self.log.grid(row=8, column=0, columnspan=2, sticky='nsew', pady=(5, 0))
        frame.rowconfigure(8, weight=1)
        self.after(100, self.poll)

    def show_about(self):
        dialog = tk.Toplevel(self)
        if os.path.isfile(self.icon_path):
            dialog.iconbitmap(self.icon_path)
        dialog.title('About')
        dialog.resizable(False, False)
        dialog.transient(self)
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text=APP_TITLE, font=('Segoe UI', 11, 'bold')).pack(pady=(0, 12))
        ttk.Label(body, text='Written by Gal Shemesh (PacketLauncher)').pack()
        url = 'https://github.com/PacketLauncher'
        link = tk.Label(body, text=url, fg='#0066cc', cursor='hand2', font=('Segoe UI', 9, 'underline'))
        link.pack(pady=(7, 16))
        link.bind('<Button-1>', lambda event: webbrowser.open(url))
        ttk.Button(body, text='OK', command=dialog.destroy).pack()
        dialog.bind('<Return>', lambda event: dialog.destroy())
        dialog.bind('<Escape>', lambda event: dialog.destroy())
        dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f'+{x}+{y}')
        dialog.grab_set()
        dialog.focus_set()

    def on_drop(self, event, index):
        # Tk's splitlist correctly handles Windows paths enclosed in braces,
        # including directory names containing spaces.
        paths = self.tk.splitlist(event.data)
        if len(paths) != 1:
            messagebox.showwarning(APP_TITLE, 'Please drop only one folder at a time.', parent=self)
            return
        path = os.path.normpath(paths[0])
        if not os.path.isdir(path):
            messagebox.showwarning(APP_TITLE, 'Please drop a folder, not a file.', parent=self)
            return
        self.vars[index].set(path)

    def browse(self, i):
        directory = filedialog.askdirectory(parent=self, initialdir=self.vars[i].get() or os.path.expanduser('~'))
        if directory:
            self.vars[i].set(directory)

    def write_log(self, message):
        self.log.configure(state='normal')
        self.log.insert('end', message + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def start(self):
        raw = [v.get().strip().strip('"') for v in self.vars]
        if not all(raw):
            messagebox.showerror(APP_TITLE, 'Please select all three folders.', parent=self)
            return
        original, modified, save = map(lambda s: Path(os.path.realpath(os.path.abspath(os.path.expandvars(s)))), raw)
        if not original.is_dir() or not modified.is_dir():
            messagebox.showerror(APP_TITLE, 'Original and Modified project folders must be existing directories.', parent=self)
            return
        if same_or_inside(original, modified) or same_or_inside(modified, original):
            messagebox.showerror(APP_TITLE, 'Original and Modified project folders must not overlap.', parent=self)
            return
        if same_or_inside(save, original) or same_or_inside(save, modified):
            messagebox.showerror(APP_TITLE, 'Select a save directory that is not inside either project folder.', parent=self)
            return
        if save.exists() and not save.is_dir():
            messagebox.showerror(APP_TITLE, 'The save path exists but is not a directory.', parent=self)
            return
        names = ('Original', 'Modified', 'Results.txt')
        if any((save / name).exists() or (save / name).is_symlink() for name in names):
            if not messagebox.askyesno('Previous Comparison Found', 'A previous comparison already exists in the selected save directory.\n\nAre you sure you want to start a new comparison?\n\nThe previous comparison will be overwritten.', parent=self):
                return
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')
        self.go.configure(state='disabled')
        self.current_save = save
        self.status.set('Comparing...')
        self.write_log(f'Comparing:\n  {original}\n  {modified}')
        threading.Thread(target=self.worker, args=(original, modified, save), daemon=True).start()

    def worker(self, original, modified, save):
        try:
            run_comparison(original, modified, save, lambda msg: self.events.put(('log', msg)))
            self.events.put(('done', None))
        except Exception as exc:
            self.events.put(('error', str(exc)))

    def show_completion(self):
        dialog = tk.Toplevel(self)
        dialog.title(APP_TITLE)
        if os.path.isfile(self.icon_path):
            dialog.iconbitmap(self.icon_path)
        dialog.resizable(False, False)
        dialog.transient(self)
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Comparison completed successfully.').pack(pady=(0, 18))
        buttons = ttk.Frame(body)
        buttons.pack(fill='x')

        def view_results():
            dialog.destroy()
            try:
                os.startfile(str(self.current_save / 'Results.txt'))
            except OSError as exc:
                messagebox.showerror(APP_TITLE, f'Could not open Results.txt:\n{exc}', parent=self)

        ttk.Button(buttons, text='View Results', command=view_results).pack(side='left')
        ttk.Button(buttons, text='OK', command=dialog.destroy).pack(side='right')
        dialog.bind('<Return>', lambda event: dialog.destroy())
        dialog.bind('<Escape>', lambda event: dialog.destroy())
        dialog.protocol('WM_DELETE_WINDOW', dialog.destroy)
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f'+{x}+{y}')
        dialog.grab_set()
        dialog.focus_set()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'log':
                    self.write_log(value)
                elif kind == 'done':
                    self.status.set('Ready')
                    self.go.configure(state='normal')
                    self.show_completion()
                elif kind == 'error':
                    self.status.set('Ready — error')
                    self.go.configure(state='normal')
                    self.write_log('ERROR: ' + value)
                    messagebox.showerror(APP_TITLE, value, parent=self)
        except queue.Empty:
            pass
        self.after(100, self.poll)


if __name__ == '__main__':
    if TkinterDnD is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_TITLE, 'Folder drag-and-drop requires tkinterdnd2.\n\nInstall it with:\npy -m pip install tkinterdnd2', parent=root)
        root.destroy()
    else:
        Application().mainloop()
