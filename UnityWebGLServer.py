#!/usr/bin/env python3
import os, socket, threading, mimetypes, urllib.request, webbrowser
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import tkinter as tk
from tkinter import filedialog, messagebox

APP_TITLE = "Unity WebGL Local/Host Server"

def get_lan_ip():
    try:
        import socket as s; sock=s.socket(s.AF_INET, s.SOCK_DGRAM); sock.connect(("8.8.8.8",80))
        ip=sock.getsockname()[0]; sock.close(); return ip
    except Exception:
        return socket.gethostbyname(socket.gethostname())

def get_public_ip(timeout=2.5):
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=timeout) as r:
            return r.read().decode("utf-8").strip()
    except Exception:
        return None

class UnityHandler(SimpleHTTPRequestHandler):
    root_dir = os.getcwd()
    enable_cors = False
    unityweb_encoding = None  # "br", "gzip", or None
    cache_control = "no-store"
    unity_mime_map = {
        ".data": "application/octet-stream",
        ".mem":  "application/octet-stream",
        ".wasm": "application/wasm",
        ".symbols.json": "application/json",
        ".js":   "application/javascript",
        ".json": "application/json",
        ".pck":  "application/octet-stream",
    }
    def translate_path(self, path):
        path = super().translate_path(path)
        cwd = os.getcwd()
        if path.startswith(cwd):
            path = os.path.join(self.root_dir, os.path.relpath(path, cwd))
        return path
    def guess_type(self, path):
        base = path
        if base.endswith(".gz"): base = base[:-3]
        if base.endswith(".br"): base = base[:-3]
        if base.endswith(".unityweb"):
            root, ext = os.path.splitext(base[:-len(".unityweb")])
            return self.unity_mime_map.get(ext, "application/octet-stream")
        root, ext = os.path.splitext(base)
        return self.unity_mime_map.get(ext, mimetypes.guess_type(base)[0] or "application/octet-stream")
    def end_headers(self):
        if self.enable_cors: self.send_header("Access-Control-Allow-Origin", "*")
        if self.cache_control: self.send_header("Cache-Control", self.cache_control)
        super().end_headers()
    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            for index in ("index.html","index.htm"):
                ip = os.path.join(path,index)
                if os.path.exists(ip): path = ip; break
            else:
                return self.list_directory(path)
        ctype = self.guess_type(path)
        try:
            f = open(path,"rb"); fs = os.fstat(f.fileno())
            self.send_response(200)
            self.send_header("Content-type", ctype)
            enc = None
            if path.endswith(".gz"): enc = "gzip"
            elif path.endswith(".br"): enc = "br"
            elif path.endswith(".unityweb"): enc = self.unityweb_encoding
            if enc: self.send_header("Content-Encoding", enc)
            if self.cache_control: self.send_header("Cache-Control", self.cache_control)
            self.send_header("Content-Length", str(fs.st_size))
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()
            return f
        except OSError:
            self.send_error(404,"File not found"); return None

class ServerThread(threading.Thread):
    def __init__(self, host, port, directory, cors, unityweb_encoding):
        super().__init__(daemon=True)
        self.host, self.port, self.directory = host, port, directory
        self.cors, self.unityweb_encoding = cors, unityweb_encoding
        self.httpd = None
    def run(self):
        H = UnityHandler
        H.root_dir = self.directory
        H.enable_cors = self.cors
        H.unityweb_encoding = self.unityweb_encoding
        H.cache_control = "no-store"
        self.httpd = ThreadingHTTPServer((self.host, self.port), H)
        try: self.httpd.serve_forever(poll_interval=0.5)
        except Exception: pass
    def stop(self):
        if self.httpd:
            self.httpd.shutdown(); self.httpd.server_close()

class App:
    def __init__(self, root):
        self.root = root; root.title(APP_TITLE); root.geometry("640x420"); root.resizable(False, False)
        self.server_thread = None
        self.mode = tk.StringVar(value="local"); self.port = tk.StringVar(value="8080")
        self.dir = tk.StringVar(value=os.getcwd()); self.cors = tk.BooleanVar(value=False)
        self.encoding = tk.StringVar(value="br")  # br, gzip, none
        row=0
        tk.Label(root,text="Unity WebGL Build Folder:").grid(row=row,column=0,sticky="w",padx=12,pady=(12,4))
        tk.Entry(root,textvariable=self.dir,width=70).grid(row=row,column=1,sticky="we",padx=8,pady=(12,4))
        tk.Button(root,text="Browse…",command=self.choose_dir).grid(row=row,column=2,padx=12,pady=(12,4)); row+=1
        fm=tk.Frame(root); tk.Label(fm,text="Mode:").pack(side="left")
        tk.Radiobutton(fm,text="Local (127.0.0.1)",variable=self.mode,value="local").pack(side="left",padx=6)
        tk.Radiobutton(fm,text="Host (0.0.0.0)",variable=self.mode,value="host").pack(side="left",padx=6)
        fm.grid(row=row,column=0,columnspan=3,sticky="w",padx=12,pady=4); row+=1
        fp=tk.Frame(root); tk.Label(fp,text="Port:").pack(side="left")
        tk.Entry(fp,textvariable=self.port,width=8).pack(side="left",padx=6)
        tk.Label(fp,text="Unity Compression:").pack(side="left",padx=(16,0))
        tk.OptionMenu(fp,self.encoding,"br","gzip","none").pack(side="left")
        tk.Checkbutton(fp,text="Enable CORS (*)",variable=self.cors).pack(side="left",padx=(16,0))
        fp.grid(row=row,column=0,columnspan=3,sticky="w",padx=12,pady=4); row+=1
        self.start_btn=tk.Button(root,text="Start Server",command=self.toggle_server,width=16)
        self.start_btn.grid(row=row,column=0,padx=12,pady=12,sticky="w")
        tk.Button(root,text="Open Local URL",command=self.open_local).grid(row=row,column=1,sticky="w"); row+=1
        self.status=tk.Label(root,text="Status: stopped",anchor="w")
        self.status.grid(row=row,column=0,columnspan=3,sticky="we",padx=12); row+=1
        tk.Frame(root,height=2,bd=1,relief="sunken").grid(row=row,column=0,columnspan=3,sticky="we",padx=12,pady=8); row+=1
        self.local_url_var=tk.StringVar(value="-"); self.lan_url_var=tk.StringVar(value="-"); self.public_url_var=tk.StringVar(value="-")
        self.build_url_row(root,"Local URL:",self.local_url_var,row); row+=1
        self.build_url_row(root,"LAN URL:",self.lan_url_var,row); row+=1
        self.build_url_row(root,"Public URL:",self.public_url_var,row); row+=1
        tk.Label(root,text=("Tip: For friends over the internet, forward the chosen TCP port on your router "
                            "to this Mac's LAN IP. Public URL works only if the port is forwarded."),
                 wraplength=600,fg="#555").grid(row=row,column=0,columnspan=3,sticky="w",padx=12,pady=(8,0))
        root.protocol("WM_DELETE_WINDOW", self.on_close)
    def build_url_row(self, root, label, var, row):
        tk.Label(root,text=label).grid(row=row,column=0,sticky="w",padx=12,pady=4)
        lbl=tk.Label(root,textvariable=var,fg="#0066cc",cursor="hand2")
        lbl.grid(row=row,column=1,sticky="w",padx=8,pady=4)
        lbl.bind("<Button-1>",lambda e,v=var:self.copy_to_clipboard(v.get()))
        tk.Button(root,text="Copy",command=lambda v=var:self.copy_to_clipboard(v.get())).grid(row=row,column=2,sticky="w",padx=12)
    def choose_dir(self):
        p=filedialog.askdirectory(title="Select Unity WebGL Build folder")
        if p: self.dir.set(p)
    def copy_to_clipboard(self,text):
        if not text or text=="-": return
        self.root.clipboard_clear(); self.root.clipboard_append(text)
        self.status.configure(text=f"Copied to clipboard: {text}")
    def open_local(self):
        url=self.local_url_var.get()
        if url and url!="-": webbrowser.open(url)
    def toggle_server(self):
        if self.server_thread: self.stop_server()
        else: self.start_server()
    def start_server(self):
        try:
            port=int(self.port.get()); assert 1<=port<=65535
        except Exception:
            messagebox.showerror(APP_TITLE,"Port must be an integer between 1 and 65535."); return
        directory=self.dir.get()
        if not os.path.isdir(directory):
            messagebox.showerror(APP_TITLE,"Please select a valid folder (your Unity WebGL build folder)."); return
        host="127.0.0.1" if self.mode.get()=="local" else "0.0.0.0"
        enc=self.encoding.get(); enc=None if enc=="none" else enc
        try:
            self.server_thread=ServerThread(host,port,directory,self.cors.get(),enc); self.server_thread.start()
        except OSError as e:
            messagebox.showerror(APP_TITLE,f"Failed to start server: {e}"); self.server_thread=None; return
        local_url=f"http://127.0.0.1:{port}/"; lan_ip=get_lan_ip(); public_ip=get_public_ip()
        self.local_url_var.set(local_url)
        self.lan_url_var.set(f"http://{lan_ip}:{port}/" if lan_ip else "-")
        self.public_url_var.set(f"http://{public_ip}:{port}/" if public_ip else "-")
        mode_text="Local" if host=="127.0.0.1" else "Host (public)"
        cors_text="ON" if self.cors.get() else "OFF"; enc_text=(self.encoding.get() or "none").upper()
        self.status.configure(text=f"Status: running — {mode_text}, port {port}, CORS {cors_text}, Unity compression: {enc_text}")
        self.start_btn.configure(text="Stop Server")
    def stop_server(self):
        try:
            if self.server_thread: self.server_thread.stop()
        finally:
            self.server_thread=None
            self.status.configure(text="Status: stopped")
            self.start_btn.configure(text="Start Server")
            self.local_url_var.set(self.lan_url_var.set(self.public_url_var.set("-")) or "-")
    def on_close(self):
        try:
            if self.server_thread: self.server_thread.stop()
        finally:
            self.root.destroy()

def main():
    root = tk.Tk(); App(root); root.mainloop()

if __name__ == "__main__":
    main()
