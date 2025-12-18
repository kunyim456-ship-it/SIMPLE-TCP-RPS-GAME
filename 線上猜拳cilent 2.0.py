import tkinter as tk
from tkinter import scrolledtext, messagebox
import socket
import threading
import json

HOST = socket.gethostbyname(socket.gethostname())
PORT = 6000
COUNTDOWN_SECONDS = 60

class RPSClientGUI:
    def __init__(self, master):
        self.master = master
        master.title(" 線上猜拳 (持久連線版) ")
        master.geometry("400x650")

        self.sock = None
        self.is_connected = False # 是否連上 Server
        self.in_game = False      # 是否在遊戲中
        self.timer_task = None 

        # --- 介面佈局 ---
        # 1. 登入區塊
        self.frame_login = tk.Frame(master)
        self.frame_login.pack(pady=10)
        tk.Label(self.frame_login, text="暱稱:").pack(side=tk.LEFT)
        self.entry_nickname = tk.Entry(self.frame_login)
        self.entry_nickname.pack(side=tk.LEFT, padx=5)
        self.entry_nickname.insert(0, "Player1") 
        self.entry_ip = tk.Entry(self.frame_login)
        self.entry_ip.pack(side=tk.RIGHT, padx=5)
        self.entry_ip.insert(0, HOST)
        self.btn_connect = tk.Button(self.frame_login, text="登入伺服器", command=self.connect_server)
        self.btn_connect.pack(side=tk.LEFT)

        # 2. [核心功能] 配對控制區 (預設隱藏或無效)
        self.frame_match = tk.Frame(master, pady=5)
        self.frame_match.pack()
        self.btn_match = tk.Button(self.frame_match, text="🔍 開始配對", font=("Arial", 14, "bold"), 
                                   bg="#4CAF50", fg="white", width=20, command=self.toggle_matchmaking)
        self.btn_match.pack()
        self.btn_match.config(state=tk.DISABLED)

        # 3. 倒數計時與狀態
        self.lbl_timer = tk.Label(master, text="", font=("Arial", 20, "bold"), fg="red")
        self.lbl_timer.pack(pady=5)
        self.lbl_status = tk.Label(master, text="請先登入...", font=("Arial", 12), fg="blue")
        self.lbl_status.pack(pady=5)

        # 4. 出拳按鈕
        self.frame_actions = tk.Frame(master)
        self.frame_actions.pack(pady=10)
        self.btn_rock = tk.Button(self.frame_actions, text="✊", font=("Arial", 20), command=lambda: self.send_move('rock'))
        self.btn_paper = tk.Button(self.frame_actions, text="✋", font=("Arial", 20), command=lambda: self.send_move('paper'))
        self.btn_scissors = tk.Button(self.frame_actions, text="✌️", font=("Arial", 20), command=lambda: self.send_move('scissors'))
        self.btn_rock.pack(side=tk.LEFT, padx=10)
        self.btn_paper.pack(side=tk.LEFT, padx=10)
        self.btn_scissors.pack(side=tk.LEFT, padx=10)
        self.toggle_game_buttons(False)

        # 5. 離開/斷線按鈕
        self.btn_leave = tk.Button(master, text="🚪 離開/斷線", font=("Arial", 10), command=self.disconnect_server)
        self.btn_leave.pack(pady=10)

        # 6. 紀錄
        self.log_area = scrolledtext.ScrolledText(master, height=10)
        self.log_area.pack(padx=10, pady=5, fill=tk.BOTH, expand=True)

    # --- 邏輯功能 ---
    def toggle_game_buttons(self, state):
        s = tk.NORMAL if state else tk.DISABLED
        self.btn_rock.config(state=s)
        self.btn_paper.config(state=s)
        self.btn_scissors.config(state=s)

    def log(self, msg):
        self.log_area.insert(tk.END, msg + "\n")
        self.log_area.see(tk.END)

    def connect_server(self):
        """Step 1: 建立 TCP 連線 (還沒配對)"""
        nick = self.entry_nickname.get()
        if not nick: return
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.entry_ip.get(), PORT))
            # 發送登入 (Type 1)
            self.sock.sendall((json.dumps({"type": 1, "nickname": nick}) + '\n').encode('utf-8'))
            
            self.is_connected = True
            self.btn_connect.config(state=tk.DISABLED)
            self.btn_match.config(state=tk.NORMAL, text="🔍 開始配對", bg="#4CAF50") # 綠色
            self.lbl_status.config(text="已登入大廳，請按配對", fg="green")
            
            threading.Thread(target=self.receive_loop, daemon=True).start()
        except Exception as e:
            messagebox.showerror("錯誤", f"連線失敗: {e}")

    def toggle_matchmaking(self):
        """Step 2: 切換 [開始配對] / [取消配對]"""
        if not self.is_connected: return

        text = self.btn_match.cget("text")
        if not self.in_game and text == "🔍 開始配對":
            # 發送 Type 6: 請求配對
            self.send_json({"type": 6})
            self.btn_match.config(text="❌ 取消配對", bg="#FF9800") # 橘色
            self.lbl_status.config(text="", fg="orange")
        else:
            # 發送 Type 7: 取消配對 (Server 需支援，若無則只改 UI)
            self.send_json({"type": 7})
            self.btn_match.config(text="🔍 開始配對", bg="#4CAF50")
            self.lbl_status.config(text="已取消，回到大廳", fg="blue")

    def send_move(self, move):
        """Step 3: 遊戲中出拳"""
        self.send_json({"type": 3, "message": move})
        self.toggle_game_buttons(False)
        self.lbl_status.config(text="已出拳，等待對手...", fg="orange")
        self.stop_countdown()

    def disconnect_server(self):
        """完全斷開 / 離開遊戲"""
        if self.in_game:
            self.send_json({"type": 5}) # 遊戲中離開
        try:
            self.sock.close()
        except: pass
        self.reset_ui()

    def send_json(self, data):
        if self.sock:
            try: self.sock.sendall((json.dumps(data) + '\n').encode('utf-8'))
            except: self.reset_ui()

    # --- 接收迴圈 (核心狀態處理) ---
    def receive_loop(self):
        f = self.sock.makefile(mode='r', encoding='utf-8')
        while self.is_connected:
            try:
                line = f.readline()
                if not line: break
                msg = json.loads(line)
                msg_type = msg.get('type')

                if msg_type == 2: # 系統訊息
                    self.lbl_status.config(text="", fg="blue")
                    self.lbl_timer.config(text="")
                    content = msg.get('message')
                    self.log(f"[系統] {content}")
                    
                    if "配對成功" in content:
                        self.master.after(0, self.game_start_ui)
                    if "對手離開房間" in content:
                        self.stop_countdown()
                    elif "回到大廳" in content:
                        self.master.after(0, self.game_over_ui_reset)
                    
                    
                elif msg_type == 4: # 結果
                    res = msg.get('result')
                    opp = msg.get('opponent_move')
                    self.log(f"★ 判決: {res} (對手: {opp})")
                    if res == 'You Win!':
                        self.lbl_status.config(text=f"你贏了！對手出 {opp}", fg="green")
                    elif res == 'You Lose!':
                        self.lbl_status.config(text=f"你輸了！對手出 {opp}", fg="red")
                    else:
                        self.lbl_status.config(text=f"平手！對手也出 {opp}", fg="blue")
                    self.lbl_timer.config(text="")
                    self.in_game = False
                    self.master.after(0, self.stop_countdown)
                    # 結果顯示後，Server 會自動送 "回到大廳" 的訊息，這裡只需顯示

            except:
                break
        self.master.after(0, self.reset_ui)

    # --- UI 狀態切換 helper ---
    def game_start_ui(self):
        #self.log_area.delete(1.0, tk.END)
        self.in_game = True
        self.btn_match.config(text="⚔️ 對戰中", state=tk.DISABLED, bg="gray")
        self.toggle_game_buttons(True)
        self.start_countdown(10)

    def game_over_ui_reset(self):
        self.in_game = False
        self.stop_countdown()
        self.toggle_game_buttons(False)
        self.btn_match.config(text="🔍 開始配對", state=tk.NORMAL, bg="#4CAF50")
        self.lbl_status.config(text="遊戲結束，請重新配對", fg="blue")
        self.lbl_timer.config(text="")

    def reset_ui(self):
        self.is_connected = False
        self.in_game = False
        self.stop_countdown()
        self.btn_connect.config(state=tk.NORMAL)
        self.btn_match.config(text="🔍 開始配對", state=tk.DISABLED, bg="gray")
        self.toggle_game_buttons(False)
        self.log("--- 已斷線 ---")

    # --- 計時器 (同前) ---
    def start_countdown(self, sec):
        self.stop_countdown()
        def count():
            nonlocal sec
            if sec > 0:
                self.lbl_timer.config(text=f"{sec}")
                sec -= 1
                self.timer_task = self.master.after(1000, count)
            else:
                self.lbl_timer.config(text="逾時")
                self.in_game = False
                self.btn_match.config(state=tk.NORMAL, text="🔍 開始配對", bg="#4CAF50")
                self.toggle_game_buttons(False)
                self.send_json({"type": 8})
        count()

    def stop_countdown(self):
        if self.timer_task:
            self.master.after_cancel(self.timer_task)
            self.timer_task = None

if __name__ == '__main__':
    root = tk.Tk()
    RPSClientGUI(root)
    root.mainloop()