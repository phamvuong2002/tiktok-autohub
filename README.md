# ⚡ TikTok AutoHub — Dell R630 Video Factory + Standalone Laptop & Oppo A57 Auto-Poster

Hệ thống tự động hóa 2 tầng chuyên nghiệp dành cho kênh TikTok Affiliate TPCN (**`@suckhoeviet.2`** & **`@suc.khoe.vang.268`**):
1. **Tầng 1 — Nhà máy Cắt & Render Video 24/7 trên Server Dell R630 (`http://192.168.1.240:8088`):**
   - Tự động quét luồng ghi `LiveVault` 45 giây/lần, nhận diện giọng nói tiếng Việt (`vi-VN`), cắt bỏ đoạn cuối vi phạm (Lazada/báo giá/giỏ hàng điện thoại), đảo 3.5 giây Hook lên đầu (`00:00`), xóa khung tím + xóa logo đỏ (`delogo`), đóng khung chữ vàng chữ đen chuẩn TikTok Pill (3–4 dòng ngắn, lề an toàn `>=110px`), sinh Caption chuẩn SEO + 5 Hashtag và ánh xạ đúng `seller_id` Shop chạy quảng cáo **GMV Max (`isAd: true`)**.
2. **Tầng 2 — Trạm Điều Khiển Độc Lập trên Laptop & Oppo A57 (`C:\TikTok_AutoHub\` • `http://localhost:8099`):**
   - **Chạy độc lập 100% trên Laptop** bằng 1 cú đúp chuột vào `Start-TikTok-AutoHub.cmd` (không cần mở phiên chat AI).
   - **Tự động tải trước (Pre-Cache) kho video Offline** từ R630 về `C:\TikTok_AutoHub\video_cache\` để khi mang **Laptop + Oppo A57 đi ra ngoài làm việc** (khác mạng với R630) vẫn có sẵn 16+ video đăng suốt cả ngày.
   - **Kết nối Oppo A57 siêu tốc & Roaming thông minh:** Cắm cáp USB 1 lần để tự khóa cổng cố định `5555`; khi mang Laptop + Oppo A57 ra quán cafe / phát Hotspot (Oppo A57 đổi IP), hệ thống tự quét dải mạng Local của Laptop trong `0.4 giây` và tự bắt tay lại với Oppo A57 bằng khóa RSA đã đồng bộ sẵn.
   - **Chuyển đổi chính xác trong 4 tài khoản TikTok trên Oppo A57:** Dùng `uiautomator` kiểm tra trang Hồ sơ và tự động chuyển đúng sang **`@suckhoeviet.2`** hoặc **`@suc.khoe.vang.268`** trước khi nạp video.
   - **Kiểm soát Chống Đăng Trùng 3 Lớp (`anti_duplicate_ledger.db`):**
     - **Lớp 1:** Khóa mã băm nhị phân `file_sha256` của từng file `.mp4` — chặn tuyệt đối việc đăng trùng 1 file video.
     - **Lớp 2:** Khóa cặp `(clip_id, channel)` — một clip nguồn LiveVault không bao giờ đăng lại lần 2 trên cùng tài khoản.
     - **Lớp 3:** Khóa `caption_sha256` + Xóa sạch toàn bộ file `AUTO_*.mp4` / `TIKTOK_CURRENT_*.mp4` cũ trong `/sdcard/DCIM/Camera/` của Oppo A57 trước khi đẩy **duy nhất 1 video** của khung giờ hiện tại.
   - **Giãn cách chuẩn 1 Tiếng / 1 Video (60 phút):** Bộ lập lịch chạy ngầm tự động giãn cách đúng 60 phút/video.

---

## 🚀 Cách Khởi Động Hàng Ngày Trên Laptop (1 Chạm)

1. Nhấp đúp vào file **[`C:\TikTok_AutoHub\Start-TikTok-AutoHub.cmd`](file:///C:/TikTok_AutoHub/Start-TikTok-AutoHub.cmd)** (hoặc biểu tượng **TikTok AutoHub** ngoài màn hình Desktop).
2. Trình duyệt tự động mở trang điều khiển: **`http://localhost:8099`**.
3. **Kết nối Oppo A57 dễ nhất:**
   - Lần đầu tiên: Cắm cáp USB từ Oppo A57 vào Laptop -> Bấm nút vàng **`[🔌 Tự Động Tìm & Nối Oppo A57]`**. Hệ thống sẽ tự kích hoạt cổng cố định `5555` trên Oppo A57.
   - Sau đó bạn có thể rút cáp USB; dù ở nhà hay mang Laptop + Oppo A57 đi ra ngoài cùng kết nối chung 1 Wi-Fi hoặc Hotspot, hệ thống đều tự tìm thấy Oppo A57!
4. Trên giao diện `http://localhost:8099`, bạn có thể:
   - Bấm **`[🔄 Test Chuyển @suckhoeviet.2]`** hoặc **`[🔄 Test Chuyển @suc.khoe.vang.268]`** để xem điện thoại tự mở TikTok và chuyển đúng tài khoản trong 4 tài khoản.
   - Bấm **`[🚀 Đăng Ngay 1 Bài]`** hoặc bật **`[⏱️ Bật Tự Động Đăng (60 Phút / Video)]`**.

---

## 📊 Báo Cáo Đối Thủ Hàng Tuần (Tách Biệt Khỏi Luồng Đăng Chính)

- Để xem báo cáo tổng hợp hàng tuần và mở Dashboard phân tích 4 kênh (`@baovesuckhoe2424`, `@phongbenhthayvichuabenh`, `@suc.khoe.vang.268`, `@suckhoeviet.2`), chạy:
  - Nhấp đúp **`C:\TikTok_AutoHub\Run-Weekly-Competitor-Report.cmd`**
  - Và mỗi tuần nhắn cho AI: *"Cập nhật dữ liệu mới nhất cho TikTok Competitor Dashboard"* để AI quét số liệu mới nhất từ TikTok cập nhật vào file `tiktok_competitor_dashboard.html`.

---

## 📂 Cấu Trúc Thư Mục Mã Nguồn

- `laptop_control_hub.py`: Web Server độc lập (`http://localhost:8099`) & Bộ lập lịch tự động 1 tiếng/video trên Laptop.
- `oppo_auto_poster.py`: Mô-đun tự động dò tìm Oppo A57 (USB / Wi-Fi / Roaming Subnet), tự chuyển 4 tài khoản TikTok và nạp duy nhất 1 video sạch vào Camera.
- `anti_dup_sync.py`: Sổ cái SQLite chống đăng trùng 3 lớp (`SHA-256`) & Bộ đồng bộ kho video Offline từ Server Dell R630 về Laptop.
- `weekly_competitor_report.py`: Công cụ xuất báo cáo tuần & mở Dashboard phân tích đối thủ (`tiktok_competitor_dashboard.html`).
- `Start-TikTok-AutoHub.cmd`: File khởi động nhanh 1 chạm trên Windows Laptop.
