# Kịch bản demo T02 — G04

Người trình bày: Nguyễn Anh Thư. Thời lượng gợi ý: 5–7 phút. Dùng fixture synthetic offline.

## Slide 1 — Bài toán

- T02 Raw QC Triage: ưu tiên 20 ảnh cần người kiểm tra trong tập 96 ảnh.
- Nếu bỏ sót ảnh lỗi, chất lượng dữ liệu downstream giảm; nếu báo động giả, tốn ngân sách review.
- Không sử dụng ảnh hoặc thông tin cá nhân thật.

## Slide 2 — Pipeline và baseline

- Baseline: xếp hạng theo Laplacian variance đảo chiều (ảnh mờ được ưu tiên), B=20.
- PoC: kết hợp blur, dark, glare cục bộ và JPEG blockiness, chuẩn hóa theo camera/light.
- Cả hai chạy offline trên cùng fixture, seed 42 và budget 20.

## Slide 3 — Chạy và kiểm tra đầu ra

- Lệnh PoC: `python -m src.main --config configs/lab.yaml --track t02 --output out/poc --run-name poc --offline --seed 42`.
- Mở `out/poc/contact_sheet.html`, xem ảnh cùng score/lý do, nhập reviewer và export decisions CSV.
- Kiểm tra `ranked_review.csv`, `review_queue.csv`, `decision.json`, `audit_log.jsonl`.

## Slide 4 — Review và quyết định

- Queue hiện có quyết định cho 20 ảnh; pipeline lưu REWORK do 14 ảnh còn được đánh dấu RECAPTURE. Nhóm xác nhận Nguyễn Anh Thư đã thực hiện review.
- Minh họa: ảnh có lóa lớn/mất tương phản; cảnh tối nhưng vẫn rõ có thể là false alarm.
- Nêu rõ giới hạn: đánh giá bằng mắt, chưa có ground truth giảng viên nên không tuyên bố Recall@20/Precision@20.
- Audit log có các sự kiện lịch sử tên reviewer cũ; giữ nguyên để bảo toàn tính append-only. Giải thích rõ reviewer hiện tại là Nguyễn Anh Thư theo thông tin nhóm.

## Slide 5 — Kết quả và việc còn lại

- Baseline chạy 0.4806 giây; PoC chạy 1.1405 giây trên 96 ảnh (Windows 11, Python 3.12.2; lần chạy gần nhất).
- Preflight: 0 lỗi; manifest: 14/14 hợp lệ; test suite kết thúc exit code 0, một số test cần GT được skip.
- Chưa có metric chính thức do thiếu GT. Cần cập nhật email Git, xác nhận Git URL, hoàn thiện references, commit/tag theo mốc thực tế.

## Demo live checklist

1. Chạy PoC offline.
2. Mở contact sheet và chỉ ra queue / lý do / thông tin ảnh.
3. Chỉ ra CSV review và audit trail; giải thích REWORK cùng 14 RECAPTURE.
4. Mở report để nêu rõ giới hạn GT và failure modes.

