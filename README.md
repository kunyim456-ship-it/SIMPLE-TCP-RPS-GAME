# SIMPLE-TCP-RPS-GAME
group project
專題名稱：[猜拳線上對戰]

作者: [柯睿丞] - [11308013A]、 [鄭明庭] - [11303009A]、[張祐齊] - [11308009A]、[馮晨豪] - [11308011A]

專題簡介:
線上猜拳

功能特色:
- ✅ [多人多組連線]
- ✅ [功能2]

系統架構
元件層級     ||程式碼對應 
Client 介面層  RPSClientGUI
Client 網路層  receive_loop
Server 大廳層  if __name__ == '__main__'
Server 配對層  matchmaking_loop (執行緒)
Server 遊戲層  class GameRoom
Server 處理層  handle_player (執行緒)

核心職責  || 說明重點

呈現與輸入  主執行緒只負責畫圖和處理按鈕點擊，保證介面永不卡死。
非阻塞接收  獨立執行緒在背景等待 Server 資料，收到資料後通知主執行緒更新畫面。
連線接入  只負責接受 TCP 連線，並將連線物件安全地放入 waiting_queue。
自動配對  在背景持續監控隊列，是整個系統的「心跳」。是從單機版升級到多房間版的關鍵。
狀態封裝  每個實例都是一個獨立的房間，負責管理該房間內的 moves 和 lock，確保多組人玩遊戲時資料不混淆。
指令執行  每個玩家專屬的監聽執行緒，收到出拳指令 (Type 3) 後觸發 judge_and_respond 函式。


協定設計

採用 JSON (JavaScript Object Notation) 作為應用層通訊協定的資料交換格式。所有的訊息都會被序列化為 JSON 字串，並以 UTF-8 編碼進行傳輸。為了確保 TCP 串流傳輸時的訊息邊界清晰，每一條完整的 JSON 訊息末尾都會加上一個 換行符號 (\n) 作為定界符 (Delimiter)。
訊息的基本結構包含一個必要的 type (整數) 欄位，用來區分訊息的功能類別：
  Type 1 (Login): 登入請求 (夾帶 nickname)。
  Type 2 (Notification): 系統公告/狀態更新 (顯示於 Client 狀態列)。
  Type 3 (Move): 出拳指令 (rock/paper/scissors)。
  Type 4 (Result): 遊戲結果 (Win/Lose/Draw 及對手出拳)。
  Type 5 (Leave): 遊戲中主動離開/斷線。
  Type 6 (Match Request): [新功能] 請求加入配對隊列。
  Type 7 (Match Cancel): [新功能] 取消配對請求。
  Type 8 (Timeout): [新功能] 客戶端回報倒數逾時 (Client -> Server)。

	範例
玩家 Alice 登入並出拳「石頭」，擊敗出「剪刀」的對手。
客戶端 (Alice): {"type": 1, "nickname": "Alice"} (說明: Alice 連線並傳送暱稱)
伺服器: {"type": 2, "message": "Game Start! 輸入 rock, paper 或 scissors"} (說明: 伺服器配對成功，通知遊戲開始)
客戶端 (Alice): {"type": 3, "nickname": "Alice", "message": "rock"} (說明: Alice 決定出石頭)
伺服器: {"type": 4, "result": "You Win!", "opponent_move": "scissors"} (說明: 伺服器判定 Alice 獲勝，並告知對手出了剪刀)

安裝與執行
需求
- Python 3.7+
- [其他依賴]
安裝
免安裝

參考資料
- Foundations of Python Network Programming
- [其他參考]
