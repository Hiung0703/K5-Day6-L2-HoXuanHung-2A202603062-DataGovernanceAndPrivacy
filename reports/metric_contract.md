# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T02 — Raw QC Triage |
| Primary metric (tên đúng như evaluator in ra) | Defect Recall@B (B=20) |
| Tăng tốt hay giảm tốt? | higher |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | image |
| Công thức + numerator / denominator | Số ảnh lỗi trong top 20 / tổng ảnh lỗi ở split eval |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Ghép chính xác theo `image_id`; xếp giảm dần theo `score` |
| Candidate pool cố định | 96 ảnh synthetic trong `fixtures/t02_raw_qc`; split giữ theo cảnh nguồn |
| Review budget B / K | B=20 |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Robust z-score theo dev, chuẩn hóa theo camera/light; trọng số mặc định blur=1.0, dark=0.8, glare=0.9, compression=0.6; ngưỡng gợi ý RECAPTURE=2.0. Đóng băng trước eval. |
| Eval split (không dùng để tune) | `eval` (40% cảnh nguồn); chỉ chấm bằng evaluator với ground truth giảng viên cung cấp |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | Bỏ sót ảnh lỗi khỏi top 20; ảnh sạch bị đưa vào top 20; báo Precision@20 cùng Recall@20 |
| Slices sẽ báo cáo (≥2) | Theo `light` và `defect_type`; thêm `camera_id` để soi lệch camera |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Bootstrap theo cảnh nguồn, không bootstrap từng ảnh độc lập |
| Ngày giờ chốt + người chốt | Người chốt: Nguyễn Anh Thư (Lead, G04); thời điểm chốt trước eval chưa được ghi nhận. Không có ground truth để chạy eval. |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
