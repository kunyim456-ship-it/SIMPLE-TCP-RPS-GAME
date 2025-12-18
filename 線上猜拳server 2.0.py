import socket
import threading
import json
import time

HOST = '0.0.0.0'
PORT = 6000
MAX_BYTES = 1024

# --- 全域變數 ---
waiting_queue = []
queue_lock = threading.Lock()

# --- 裁判邏輯 ---
def get_winner(move1, move2):
    if move1 == move2: return 'draw'
    rules = {'rock': 'scissors', 'scissors': 'paper', 'paper': 'rock'}
    if move1 not in rules or move2 not in rules: return 'error'
    return 'p1' if rules.get(move1) == move2 else 'p2'

# --- 遊戲房間 ---
class GameRoom:
    
    def __init__(self, player1, player2):
        self.p1 = player1
        self.p2 = player2
        self.moves = {}
        self.lock = threading.Lock()
        self.event = threading.Event() # 用來通知遊戲結束
        self.game_active = True
        print(f"[配對成功] {self.p1['nickname']} vs {self.p2['nickname']}")

    def start(self):
        # 通知雙方遊戲開始
        self.send_json(self.p1['sock'], {"type": 2, "message": f"配對成功！對手是 {self.p2['nickname']}。請出拳！"})
        self.send_json(self.p2['sock'], {"type": 2, "message": f"配對成功！對手是 {self.p1['nickname']}。請出拳！"})

        # 注意：這裡不再開啟新執行緒，而是讓原本的 client_handler 進入遊戲迴圈
        # 我們只需要設定狀態，讓外部的迴圈知道「現在是遊戲時間」
        self.p1['room'] = self
        self.p2['room'] = self
        self.p1['state'] = 'GAME'
        self.p2['state'] = 'GAME'
    def send_json(self, sock, msg_dict):
        try:
            sock.sendall((json.dumps(msg_dict) + '\n').encode('utf-8'))
        except:
            pass

    def handle_move(self, player_obj, move):
        """處理出拳邏輯"""
        with self.lock:
            if not self.game_active: return
            
            print(f"[房間] {player_obj['nickname']} 出拳: {move}")
            self.moves[player_obj['addr']] = move
            
            if len(self.moves) == 2:
                self.judge_and_respond()
                self.end_game(reason="遊戲結束")

    def judge_and_respond(self):
        """判決與結算"""
        m1 = self.moves[self.p1['addr']]
        m2 = self.moves[self.p2['addr']]
        winner = get_winner(m1, m2)

        p1_res = "You Win!" if winner == 'p1' else ("Draw" if winner == 'draw' else "You Lose!")
        p2_res = "You Win!" if winner == 'p2' else ("Draw" if winner == 'draw' else "You Lose!")
        
        # 傳送 Type 4 結果
        self.send_json(self.p1['sock'], {"type": 4, "result": p1_res, "opponent_move": m2})
        self.send_json(self.p2['sock'], {"type": 4, "result": p2_res, "opponent_move": m1})


        # 結束這一局，但不斷線
        print(f"[房間] 判決完成: {self.p1['nickname']} ({m1}) vs {self.p2['nickname']} ({m2}) => {winner}")

    def handle_quit(self, leaver):
        """處理有人中途離開"""
        winner = self.p2 if leaver == self.p1 else self.p1
        self.send_json(winner['sock'], {"type": 2, "message": "對手離開房間，您獲勝！"})
        self.end_game(reason="對手離開")

    def end_game(self, reason, overtime=False):
        """遊戲結束清理"""
        if not self.game_active: return
        self.game_active = False

        print(f"[結束] 房間關閉: {reason}")

        if overtime:
            # 若是逾時，通知雙方
            self.send_json(self.p1['sock'], {"type": 2, "message": "逾時未出拳。"})
            self.send_json(self.p2['sock'], {"type": 2, "message": "逾時未出拳。"})
        
        # 將雙方狀態設回 IDLE (發呆)，這樣他們的迴圈就會回到大廳
        self.p1['state'] = 'IDLE'
        self.p2['state'] = 'IDLE'
        self.p1['room'] = None
        self.p2['room'] = None
        time.sleep(3)
        # 通知回到大廳 (Type 2 包含 '大廳' 關鍵字)
        reset_msg = {"type": 2, "message": "遊戲結束，回到大廳。"}
        self.send_json(self.p1['sock'], reset_msg)
        self.send_json(self.p2['sock'], reset_msg)


# --- Client 生命週期管理 ---
def client_handler(sock, addr):
    print(f"[連線] {addr}")
    player = {
        'sock': sock, 
        'addr': addr, 
        'nickname': 'Unknown', 
        'state': 'IDLE', # 狀態: IDLE (大廳), QUEUE (排隊中), GAME (遊戲中)
        'room': None
    }

    try:
        # 1. 讀取暱稱
        sock.settimeout(None)
        f = sock.makefile(mode='r', encoding='utf-8')
        login_data = f.readline()
        if not login_data: return
        player['nickname'] = json.loads(login_data).get('nickname', 'Unknown')
        print(f"[登入] {player['nickname']} 進入大廳")
        
        sock.sendall((json.dumps({"type": 2, "message": f"歡迎 {player['nickname']}，請按 [開始配對]"}) + '\n').encode('utf-8'))

        # 2. 進入主迴圈 (無限復活)
        while True:
            # 等待 Client 傳送指令
            data = f.readline()
            if not data: break # 斷線
            
            msg = json.loads(data)
            msg_type = msg.get('type')

            # --- 狀態機邏輯 ---
            if player['state'] == 'IDLE':
                # 在大廳，只接受 Type 6 (開始配對)
                if msg_type == 6:
                    print(f"[排隊] {player['nickname']} 加入隊列")
                    player['state'] = 'QUEUE'
                    with queue_lock:
                        waiting_queue.append(player)
                    sock.sendall((json.dumps({"type": 2, "message": "正在搜尋對手..."}) + '\n').encode('utf-8'))

            elif player['state'] == 'QUEUE':
                # 排隊中，如果收到 Type 7 (取消配對)
                if msg_type == 7:
                    print(f"[取消] {player['nickname']} 取消排隊")
                    player['state'] = 'IDLE'
                    with queue_lock:
                        if player in waiting_queue: waiting_queue.remove(player)
                    sock.sendall((json.dumps({"type": 2, "message": "已取消配對，回到大廳。"}) + '\n').encode('utf-8'))

            elif player['state'] == 'GAME':
                # 遊戲中，接受 Type 3 (出拳) 或 Type 5 (離開)
                room = player['room']
                if room:
                    if msg_type == 3:
                        room.handle_move(player, msg.get('message').strip().lower())
                    elif msg_type == 5:
                        room.handle_quit(player)
                    elif msg_type == 8:
                        print(f"[逾時] {player['nickname']} 未出拳")
                        room.end_game(reason="逾時未出拳", overtime=True)

    except Exception as e:
        print(f"[異常] {player['nickname']} 斷線: {e}")
    finally:
        # 清理殘留狀態
        if player in waiting_queue: waiting_queue.remove(player)
        if player['room']: player['room'].handle_quit(player)
        try: sock.close()
        except: pass
        print(f"[斷線] {player['nickname']} 離開伺服器")

def overtime():
    pass

# --- 配對迴圈 ---
def matchmaking_loop():
    while True:
        with queue_lock:
            if len(waiting_queue) >= 2:
                p1 = waiting_queue.pop(0)
                p2 = waiting_queue.pop(0)
                # 建立房間並啟動 (這會改變 p1, p2 的 state 為 GAME)
                room = GameRoom(p1, p2)
                room.start()
        time.sleep(0.5)

if __name__ == '__main__':
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(20)
    print(f"=== 猜拳 Server (持久連線版) 啟動 ===")
    
    threading.Thread(target=matchmaking_loop, daemon=True).start()

    while True:
        sock, addr = server.accept()
        threading.Thread(target=client_handler, args=(sock, addr), daemon=True).start()