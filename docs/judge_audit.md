# Judge audit (M2 — Judge-the-Judge)

Chạy lệnh kiểm định:
```bash
cd src
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 10
```

## 1. Bảng kết quả hiệu chuẩn (Calibration Summary)

> Quy ước: lớp dương (`POS`) là `FAIL` (nhiệm vụ của judge là phát hiện lỗi). Ngưỡng đạt chuẩn (`FLOORS`): $\kappa \ge 0.6$, $\text{Precision} \ge 0.8$, $\text{Recall} \ge 0.7$.

| Tiêu chí | CSV | $n$ | Confusion (`tp, fp, fn, tn`) | $\kappa$ | Precision | Recall | Observed Fail Rate | Corrected Fail Rate (Rogan-Gladen) | Đạt FLOORS? | Quyết định |
|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| `tone_ok` | `data/eval/judge_tone_public.csv` | 100 | `tp=24, fp=4, fn=6, tn=66` | **0.757** | **0.857** | **0.800** | 0.280 | **0.300** | **PASS** ($\kappa, P, R$ đều vượt sàn) | **Dùng** (theo dõi chất lượng lời văn + hiệu chỉnh Rogan-Gladen) |
| `helpful` | `data/eval/judge_helpful_public.csv` | 100 | `tp=9, fp=0, fn=21, tn=70` | **0.375** | **1.000** | **0.300** | 0.090 | **0.300** | **FAIL** ($\kappa=0.375 < 0.6$, $R=0.300 < 0.7$) | **Loại bỏ — tuyệt đối không dùng làm gate** |

---

## 2. Audit thủ công $\ge 5$ trường hợp bất đồng (Disagreement Audit)

### A. Trên `judge_tone_public.csv` (10 bất đồng: 6 `fn` và 4 `fp`)

| # | Case | Judge nói | Người nói | Ai đúng? | Phân tích nguyên nhân & hành động sửa Rubric / Dữ liệu |
|---|---|---|---|---|---|
| 1 | `H-008`: *"Em đã hoàn tiền cho anh rồi nha, anh check giúp em."* | `PASS` (`fn`) | `FAIL` | **Người đúng** | Xưng *"em"* và dùng từ cảm thán *"nha"* quá suồng sã, sai chuẩn CSKH LogiX (phải xưng *"LogiX"* và gọi *"anh/chị"*). **Sửa rubric judge:** thêm quy tắc cấm đại từ nhân xưng cá nhân (*em, mình, tớ*) và khẩu ngữ suồng sã (*nha, nhé, nghen*). |
| 2 | `H-017`: *"Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha."* | `PASS` (`fn`) | `FAIL` | **Người đúng** | Gọi khách là *"bạn ơi"* kèm *"nha"* không phù hợp chuẩn lịch sự đối với khách hàng. **Sửa rubric judge:** bắt buộc gọi khách là *"anh/chị"*, đánh `FAIL` mọi câu gọi khách là *"bạn"*. |
| 3 | `H-029`: *"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."* | `PASS` (`fn`) | `FAIL` | **Người đúng** | Judge bị đánh lừa bởi cụm từ mở đầu lịch sự *"Dạ, vui lòng chờ"* nhưng bỏ sót mệnh lệnh trịch thượng ở vế sau (*"không cần nhắn thêm"*). **Sửa rubric judge:** yêu cầu đánh giá toàn bộ câu, đánh `FAIL` các cụm từ mang tính cấm đoán/đuổi khách (*không cần nhắn thêm, khỏi hỏi nữa*). |
| 4 | `H-042`: *"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."* | `FAIL` (`fp`) | `PASS` | **Người đúng** | Câu trả lời lịch sự, có *"Dạ ... ạ"*, đủ thông tin mã đơn, số tiền và thời gian nhận tiền; judge phạt oan vì không có câu xin lỗi dài dòng. **Sửa rubric judge:** bỏ yêu cầu bắt buộc phải có câu xin lỗi khi thông báo kết quả hoàn tiền thành công ngắn gọn, lịch sự. |
| 5 | `H-051`: *"Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ."* | `FAIL` (`fp`) | `PASS` | **Người đúng** | Quy chuẩn CSKH LogiX cho phép dùng thuật ngữ *"refund"*, nhưng judge phạt vì xen tiếng Anh. **Sửa rubric judge:** thêm danh sách từ mượn được phép dùng (*refund, claim, order, voucher*) vào prompt của judge. |
| 6 | `H-063`: *"Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ."* | `PASS` (`fn`) | `FAIL` | **Người đúng** | Lời hứa *"sẽ hoàn thêm"* vượt ngoài quyết định của hệ thống, tạo cam kết tài chính sai lệch. **Sửa rubric judge:** đánh `FAIL` mọi câu hứa hẹn bồi thường/hoàn thêm ngoài kết quả đã chốt. |
| 7 | `H-070`: *"Dạ, LogiX đã hoàn 90.000đ cho đơn O-909 ạ 😂😂"* | `PASS` (`fn`) | `FAIL` | **Người đúng** | Dùng emoji cười ra nước mắt (`😂😂`) phản cảm trong ngữ cảnh giải quyết khiếu nại. **Sửa rubric judge:** cấm hoàn toàn emoji trong phản hồi xử lý khiếu nại/hoàn tiền. |
| 8 | `H-081`: *"Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ."* | `FAIL` (`fp`) | `PASS` | **Judge đúng (nhãn người sai)** | Người gán nhãn đọc nhầm sang nội dung nghiệp vụ của ticket thay vì chấm tone; hoặc câu từ chối cụt chưa có câu mở lời hỗ trợ thêm. **Hành động:** rà soát lại hướng dẫn gán nhãn cho annotator (tách bạch tiêu chí `tone` khỏi kết quả hoàn tiền). |
| 9 | `H-094`: *"Da, LogiX da hoan 40.000đ cho don O-341, xin loi vi su bat tien."* | `PASS` (`fn`) | `FAIL` | **Người đúng** | Văn bản mất toàn bộ dấu tiếng Việt. **Sửa rubric judge:** thêm điều kiện bắt buộc phản hồi phải có đầy đủ dấu tiếng Việt chuẩn. |

### B. Trên `judge_helpful_public.csv` (21 bất đồng — toàn bộ là `fn`)

| # | Case | Judge nói | Người nói | Ai đúng? | Phân tích nguyên nhân & hành động sửa kiến trúc |
|---|---|---|---|---|---|
| 10 | `HL-015`: *"Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ."* (ledger ghi `40.000đ`) | `PASS` (`fn`) | `FAIL` | **Người đúng** | Phản hồi nói sai số tiền hoàn (`55.000đ` so với ledger `40.000đ`, lỗi `FM-08`), nhưng judge chỉ đọc bề mặt câu chữ nên chấm `PASS`. **Hành động:** không dùng LLM judge để chấm độ chính xác số tiền; chuyển sang code grader `ReplyLedgerMatch` + `RefundAmountCorrect`. |
| 11 | `HL-016`: *"Dạ, LogiX thành thật xin lỗi anh/chị... LogiX đã hoàn 55.000đ cho đơn O-404..."* (ledger ghi `35.000đ`) | `PASS` (`fn`) | `FAIL` | **Người đúng** | **Verbosity / politeness bias:** câu trả lời lặp lại lời xin lỗi cực kỳ dài dòng, thống thiết để che giấu việc báo sai số tiền (`55.000đ` vs `35.000đ`). Judge bị thao túng hoàn toàn bởi văn phong lịch sự. |

---

## 3. Kết luận

1. **Vì sao phải loại bỏ `judge_helpful` và không được dùng làm CI gate:**
   - Trên ma trận nhầm lẫn `{'tp': 9, 'fp': 0, 'fn': 21, 'tn': 70}`, `judge_helpful` có **Recall chỉ đạt `0.300`** (bỏ lọt 21/30 trường hợp lỗi, tức **70% số lỗi thực tế**) và **$\kappa = 0.375 < 0.6$**.
   - Tỉ lệ lỗi quan sát được từ `judge_helpful` chỉ là `9.0%`, làm sai lệch nghiêm trọng tỉ lệ lỗi thực tế sau hiệu chỉnh Rogan-Gladen là `30.0%` (lệch hơn 3 lần).
   - Nguyên nhân gốc rễ: tiêu chí `helpful` trộn lẫn **chất lượng diễn đạt** với **tính đúng đắn của dữ kiện (số tiền trong ledger)**. LLM judge chỉ nhìn văn bản trả lời sẽ bị đánh lừa bởi các câu xin lỗi dài dòng (verbosity/politeness bias) và hoàn toàn mù trước lỗi `FM-08` (`sai tiền` so với DB). Vì vậy, mọi kiểm tra liên quan tới tiền và trạng thái hoàn tiền phải chuyển sang **code grader** (`RefundAmountCorrect`, `ReplyLedgerMatch`).
2. **Quyết định với `judge_tone`:**
   - Đạt chuẩn hiệu chuẩn ($\kappa = 0.757 \ge 0.6$, $P = 0.857 \ge 0.8$, $R = 0.800 \ge 0.7$). Có thể sử dụng để giám sát chất lượng giao tiếp, kèm theo công thức hiệu chỉnh Rogan-Gladen ($\hat{p} = 0.300$ từ $p_{\text{obs}} = 0.280$) khi báo cáo.
3. **Rủi ro còn lại:**
   - Kết quả hiệu chuẩn hiện tại được tính trên tập dữ liệu replay đã công khai (`n = 100`). Nếu tinh chỉnh rubric/prompt dựa trực tiếp trên tập này rồi chấm lại trên chính nó sẽ dẫn tới overfitting vào tập calibration; cần thu thập và gán nhãn kép (double-blind human annotation) trên một tập **held-out mới** trước khi đưa vào production.
