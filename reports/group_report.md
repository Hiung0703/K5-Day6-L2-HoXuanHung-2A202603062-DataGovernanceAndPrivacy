# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số phải lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`) — không gõ tay, không làm tròn mất đơn vị.
> 3–5 trang (hoặc README + report.md tương đương).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G04 |
| Challenge | T02 · Raw QC Triage |
| Thành viên + vai trò | Nguyễn Anh Thư (MSSV 2A202603084) — Lead, người trình bày và thành viên duy nhất; tự thực hiện toàn bộ tác vụ |
| Git URL | Chưa xác nhận đây là remote nộp bài của nhóm; cần xác nhận/cập nhật |
| Tag `demo-180m` (commit) | Chưa tạo |
| Tag `final-24h` (commit) | Chưa tạo |
| Deadline (giờ VN) | Đúng hạn (chưa có ngày/giờ cụ thể) |

## 01 · Problem statement

- Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai? Nhóm thu thập dữ liệu và người dùng mô hình downstream; bỏ sót ảnh lỗi làm giảm chất lượng dữ liệu, báo động giả làm lãng phí lượt review.
- Điểm nghẽn cụ thể: Chỉ có ngân sách review 20 ảnh, nên cần ưu tiên ảnh nghi mờ, lóa, thiếu sáng hoặc nén lỗi.
- Đầu vào → đầu ra: 96 ảnh synthetic cùng metadata camera/ánh sáng → `ranked_review.csv`, queue/contact sheet 20 ảnh, quyết định và audit log.
- Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval): HOLD khi chưa review đủ queue hoặc còn escalation; REWORK khi ảnh được reviewer xác nhận cần chụp lại; GO khi review đủ queue và không còn ảnh cần chụp lại/escalation.
- Giả định của nhóm (cần DPO/legal/domain owner xác nhận): Dùng fixture synthetic CC0; không dùng ảnh/người/biển số thật.

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 56 | Fixture synthetic của repo | CC0-1.0 | Có |
| eval / heldout | 40 | Fixture synthetic của repo; chỉ evaluator dùng nhãn GT | CC0-1.0 | Có |

- Schema & class mapping: `image_id, path, camera_id, light, split`; defect type gồm none/blur/glare/dark/compression.
- Seed: 42 · Cách chia split (theo scene/group/segment?): fixture tách theo cảnh nguồn; không chia lại theo ảnh.
- `manifest.csv` verified (sha256): `python -m tools.verify_manifests` — 14 manifests, 0 lỗi; `python -m tools.preflight` kiểm tra fixture T02 thành công.
- Dữ liệu thật dùng (nếu có) và cách xây GT cho nó: Không dùng; GT fixture do giảng viên giữ riêng.

## 03 · Research & design

- 2–3 references (URL + ngày xem) và **vì sao** chọn kỹ thuật: Pertuz et al. tổng hợp các focus measure, gồm variance of Laplacian, làm căn cứ cho baseline; OpenCV mô tả phép tính Laplacian dùng trong bộ lọc; ACDC của ETH Zurich cho thấy điều kiện lái xe bất lợi như ban đêm cần được coi là slice riêng. Các nguồn này hỗ trợ lựa chọn đặc trưng và thiết kế kiểm tra, không chứng minh hiệu quả PoC trên fixture này.
- Sơ đồ data flow (input → process → rank/QC → review → decision → report): manifest/images → đặc trưng blur/brightness/glare/blockiness → rank top-20 → reviewer override → GO/HOLD/REWORK → CSV/JSON/audit.
- Thành phần offline (model/weights + checksum + license nếu có): Không dùng model hoặc weights; chỉ Pillow/NumPy/SciPy và fixture synthetic.
- Trade-offs đã cân nhắc: Baseline Laplacian đơn giản nhưng nhạy khác biệt camera/điều kiện sáng; PoC chuẩn hóa robust theo camera/light và kết hợp bốn tín hiệu dễ giải thích, nhưng cần lưu ý kích thước mẫu nhỏ.

## 04 · Baseline vs PoC

- Baseline (mô tả, version/config, commit): `src.examples.laplacian_baseline`; score = âm Laplacian variance toàn ảnh; B=20, seed=42, offline. Run thành công trên cùng 96 ảnh. Runtime 0.4806 giây; SHA lúc chạy `b0ce8bf` (working tree khi chạy chưa commit).
- PoC (mô tả, version/config, commit): `src.pipeline`; robust anomaly scores theo camera/light cho blur, dark, local glare và JPEG blockiness; weights 1.0/0.8/0.9/0.6, recapture threshold 2.0. B=20, seed=42, offline. Run thành công; runtime 1.1405 giây; 96 ảnh, queue 20; SHA lúc chạy `b0ce8bf` (working tree khi chạy chưa commit).
- Cùng budget / cùng heldout / cùng seed: baseline và PoC dùng cùng fixture, seed 42, offline, budget 20. So sánh metric chính thức chưa thể lập vì ground truth/evaluator input chưa được cung cấp.

**Bảng 1 · Baseline vs PoC & hard slices** — dán output của
`python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json`:

| Metric (unit) | Baseline | PoC | Δ & chú thích |
|---|---|---|---|
| Primary: Defect Recall@20 | Chưa có GT | Chưa có GT | Chưa tính; không suy diễn nhãn |
| Hard-slice: theo light/defect | Chưa có GT | Chưa có GT | Cần evaluator/GT giảng viên |
| Review@20 / miss / FP | Chưa có GT | Chưa có GT | B=20 |
| Runtime / 100 items | 0.5006 giây | 1.1880 giây | Run time chia theo 96 ảnh rồi nhân 100; Windows 11, Python 3.12.2 |

## 05 · Evaluation protocol

- Công thức primary metric, đơn vị đánh giá, TP/FP/FN, denominator: Defect Recall@B, đơn vị ảnh, B=20; số ảnh lỗi trong top 20 / tổng ảnh lỗi ở split eval; ghép theo `image_id`. Định nghĩa đã ghi ở `reports/metric_contract.md`.
- Threshold / budget B / K và lúc chốt: B=20; ngưỡng RECAPTURE=2.0; weights blur=1.0, dark=0.8, glare=0.9, compression=0.6 theo cấu hình. Thời điểm/người chốt trước eval chưa được ghi nhận.
- Độ bất định (CI/bootstrap/variance) khi N nhỏ: kế hoạch bootstrap theo cảnh nguồn trong metric contract; chưa tính do không có GT.
- Lệnh evaluate chính xác: Chưa chạy; cần gói GT/evaluator của giảng viên. Không dùng nhãn tự tạo để báo cáo điểm chính thức.

## 06 · Result slices

| Slice | N | Baseline | PoC | Ghi chú |
|---|---|---|---|---|
| day | 56 | Chưa có GT | Chưa có GT | Slice theo `light`; chưa thể so sánh defect recall |
| night | 20 | Chưa có GT | Chưa có GT | Queue PoC có night items; kết quả chỉ qualitatively reviewed |
| dusk | 20 | Chưa có GT | Chưa có GT | Slice theo `light`; chưa thể so sánh defect recall |

- Failure case 1 (ảnh/metadata + root cause): `img_17_2` có lóa lớn ở vùng giữa, làm giảm tương phản đường và nền; được đánh dấu RECAPTURE trong review hiện có.
- Failure case 2: `img_13_3`, `img_17_3`, `img_23_3` bị mờ/tối nặng theo quan sát hình; `img_18_2` là ví dụ cảnh đêm tương đối rõ nhưng bị xếp vào queue, thể hiện nguy cơ false alarm do ánh sáng theo cảnh. Đây là đánh giá định tính, chưa xác nhận bằng GT.
- Latency / compute (máy, CPU, ms/item): Windows 11, Python 3.12.2, AMD64 Family 23 Model 96 Stepping 1; baseline 5.01 ms/ảnh, PoC 11.88 ms/ảnh (runtime tổng/96, lần chạy gần nhất).

## 07 · Human & decision

- Review queue (file, B, cách ưu tiên): `out/poc/review_queue.csv`, B=20, score giảm dần; contact sheet offline tại `out/poc/contact_sheet.html`.
- Cách override + audit log (`out/poc/audit_log.jsonl`): `review_queue_reviewed.csv` có quyết định cho 20/20 dòng; nhóm xác nhận Nguyễn Anh Thư là người thực hiện review. Các sự kiện audit đã ghi trước đó được giữ nguyên để bảo toàn tính append-only; các sự kiện lịch sử này mang tên reviewer cũ và không được xem là bằng chứng định danh cho reviewer hiện tại.
- Decision policy + `reason_code` + owner: REVIEW_PENDING → HOLD; queue còn RECAPTURE → REWORK; escalation → HOLD; hết queue và không còn cờ → GO. Owner đã cấu hình cho G04 là `Nguyễn Anh Thư - Lead`.
- Kết quả hiện lưu: 20 dòng có quyết định; pipeline lưu `REWORK`, reason `RECAPTURE_REQUIRED`, 14 ảnh cần chụp lại. Đây là kết quả review queue, không phải metric ground truth.
- Khi nào HOLD/REWORK thay vì tự động release: HOLD khi thiếu review/escalation; REWORK khi reviewer xác nhận còn ảnh cần chụp lại.

## 08 · Reproduce & tests

```bash
.\.venv\Scripts\python.exe -m src.main --config configs/lab.yaml --track t02 --output out/poc --run-name poc --offline --seed 42
# Sau khi giảng viên cung cấp gói GT:
.\.venv\Scripts\python.exe -m src.evaluate --track t02 --pred out/poc/ranked_review.csv --run-name poc --out reports/metrics_poc.json
.\.venv\Scripts\python.exe -m pytest -q
```

- Output của `pytest -q`: pass (exit code 0); một số kiểm thử cần GT được skip.
- `python -m tools.preflight`: 0 FAIL, 2 WARN (gói `data/real` và model tùy chọn không có; không cần cho T02 synthetic offline). `python -m tools.verify_manifests`: 14 manifests, 0 lỗi.
- Máy / CPU / OS / Python: Windows 11 · AMD64 Family 23 Model 96 Stepping 1 · Python 3.12.2 · git sha lúc chạy `b0ce8bf`; thay đổi hiện tại chưa commit.

## 09 · Limitations & ethics

- Rủi ro pháp lý / PII / license: Fixture hiện là synthetic CC0; không dùng ảnh thật/PII trong PoC này.
- Điều chưa biết; false alarms; nếu scale 10× thì sao: Fixture nhỏ (96 ảnh); độ ổn định theo camera/ánh sáng và compression cần đánh giá thêm trên dữ liệu được phép sử dụng.
- Không tuyên bố "đạt GDPR / luật Việt Nam" từ checklist tự động; giả định cần DPO/legal xác nhận: Không đưa ra tuyên bố tuân thủ pháp luật từ pipeline QC.
- Kế hoạch cải tiến: Chạy hidden eval, xem false alarms theo camera/light, thêm dữ liệu hợp lệ và hiệu chỉnh trọng số chỉ trên dev.

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence** (đối chiếu với `git shortlog -sne --all` và `reports/team_contributions.csv`)

| Học viên | Git author/email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|---|
| Nguyễn Anh Thư (2A202603084) | 26ai.thuna@vinuni.edu.vn | Lead; thành viên duy nhất | Implementation commit `f0850bf`; có hỗ trợ AI khi triển khai/reporting | Có |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa (không chép nguyên văn) |
|---|---|---|
| https://isp-utb.github.io/seminario/papers/Pattern_Recognition_Pertuz_2013.pdf | 2026-11-14 | Khảo sát focus measure, trong đó có variance of Laplacian; hỗ trợ lý do chọn baseline sharpness, không xác nhận threshold cho tập này. |
| https://docs.opencv.org/4.x/d5/db5/tutorial_laplace_operator.html | 2026-11-14 | Tài liệu phép Laplacian của OpenCV; dùng để mô tả toán tử hình ảnh của baseline. |
| https://acdc.vision.ee.ethz.ch/overview | 2026-11-14 | Tài liệu dataset adverse driving conditions; làm cơ sở xem ban đêm là điều kiện cần slice riêng, không dùng dữ liệu ACDC trong PoC. |

---

**Bảng 3 · Checklist chốt khi nộp**

- [ ] Xác nhận Git URL của nhóm và tạo tag cuối; input mẫu không chứa PII thật.
- [ ] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [ ] Có baseline/PoC metrics, ≥1 failure case, reviewer evidence, decision log.
- [ ] Có license/source provenance, data splits, seed, offline environment, GT/eval N.
- [ ] Cập nhật Git author/email, tạo commit thực chất và ghi SHA minh bạch trong bảng trên.
