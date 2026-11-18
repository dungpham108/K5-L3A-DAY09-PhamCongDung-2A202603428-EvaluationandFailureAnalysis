# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời câu hỏi: **bước nào là bước sai đầu tiên**, và bài kiểm thử (regression test) nào sẽ chặn được nó ở mọi lần chạy sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

---

## Case 1 (Anchor FM-03): `seeded_regression C-002@11` — Tin số ngày trễ trong ticket hơn DB

| Trường | Nội dung |
|---|---|
| **Trial** | `seeded_regression C-002@11` (cũng xuất hiện trên `swarm C-002@55`), trong report `reports/eval_seeded_regression.json` |
| **Triệu chứng** | `TrialPass` (`pass_rate`), `RefundAmountCorrect` (`refund_amount_correct`), `DbFactKept` (`db_fact_kept`), và `ReplyLedgerMatch` (`reply_ledger_match`) cùng **FAIL**. Phản hồi `reply` nói *"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."* và `refund_ledger` ghi hoàn `20.000đ` (`status="resolved"`), trong khi nhãn đúng của `C-002` là `status="denied"`, `refund_vnd=0`. |
| **Bước sai đầu tiên** | **Step 3** · `model_override` · `{"delay_days": 5}` |
| **Vì sao là bước *đầu tiên*** | Ở **Step 1** (`handoff`), yêu cầu kiểm tra chính sách được chuyển đúng chuẩn `handoff.v1`. Ở **Step 2** (`investigator`), công cụ đọc DB trả về dữ kiện chuẩn xác: `{"lookup_order": {"visible": true, "order": {"order_id": "O-202", "status": "delivered", "delay_days": 2, "shipping_fee_vnd": 20000}}}` và `compute_compensation` ban đầu tính `0đ` (vì `delay_days=2 < 3`). Tuy nhiên ngay tại **Step 3** (`model_override`), agent lấy con số `"5 ngày"` trong câu chữ của ticket để ghi đè `order["delay_days"] = 5`, kéo theo **Step 4** (`quote` tính lại `amount_vnd=20000`) và **Step 6** (ghi ledger `20.000đ` + trả lời khách đã hoàn tiền). |
| **Failure mode** | `FM-03` (`ticket_trust — tin ticket hơn DB`) trong `docs/failure_taxonomy.md` |
| **Đối chứng (`fixed C-002@11`)** | Trên shape `fixed` cùng `C-002@11`, sau **Step 2** (`investigator` trả `delay_days=2`), agent giữ nguyên dữ liệu DB, **không có Step `model_override`**, nên **Step 3** (`quote`) giữ `{"amount_vnd": 0, "reason": "not_eligible"}` và **Step 4** (`reply`) trả về đúng `status="denied"`, `ledger.refund_vnd=0`. |
| **Regression test** | `tests/test_lab9_graders.py::test_override_event_breaks_db_fact` và `tests/test_lab9_graders.py::test_trace_case_c002_seeded_regression_vs_fixed` (sử dụng `DbFactKept` ở mức step và `RefundAmountCorrect` ở mức outcome; cả hai đều **FAIL** trên `seeded_regression C-002@11` và **PASS** trên `fixed C-002@11`). |
| **Chưa chắc chắn** | Trace chỉ cho thấy `order["delay_days"]` bị ghi đè thành `5` (và có hay không event `model_override`); nếu một biến thể ẩn (`quiet_override`) ghi đè biến `order["delay_days"]` trong bộ nhớ mà không gọi `trace.add("model_override", ...)`, chỉ nhìn event `model_override` sẽ không thấy — khi đó phải kết hợp đối chiếu `investigator.lookup_order.order.delay_days` với `quote` và `RefundAmountCorrect` trên ledger. |

---

## Case 2 (Anchor FM-05 & FM-08): `seeded_regression C-014@11` — Tự trừ hoàn trước (`pre_deducted`) & báo sai số tiền (`misreport`)

| Trường | Nội dung |
|---|---|
| **Trial** | `seeded_regression C-014@11`, trong report `reports/eval_seeded_regression.json` |
| **Triệu chứng** | `TrialPass` (`proposal_mismatch`), `RefundAmountCorrect` (`ledger=90000 != label=120000`) và `ReplyLedgerMatch` (`reply_amounts=[120000] != ledger=90000`) cùng **FAIL**. `reply` báo với khách *"Dạ, LogiX đã hoàn 120.000đ cho đơn O-515."*, nhưng `refund_ledger` chỉ ghi `90.000đ` (nhãn đúng là `proposal_amount=150000`, `refund_vnd=120000`). |
| **Bước sai đầu tiên** | **Step 5** · `proposal` · `{"amount_vnd": 120000}` |
| **Vì sao là bước *đầu tiên*** | **Step 1** (`handoff`), **Step 2** (`investigator` đọc đơn `O-515`: `delay_days=5`, `damage_verified=true`), **Step 3** (`quote` trả `amount_vnd=150000`, lấy `max(30000, 150000)`), và **Step 4** (`refund_history` đọc lịch sử đã hoàn `30000`) đều đúng. Sai lầm bắt đầu ở **Step 5** (`proposal`): agent tự lấy `150000 - 30000 = 120000` trước khi gọi `issue_refund(conn, "C-014", 120000)`. Vì host tự động trừ phần đã hoàn (`30000`) một lần nữa nên ledger chỉ ghi `90000`; sau đó ở **Step 6** (`reply`), agent lại lấy số `proposal=120000` để báo cho khách (sinh thêm lỗi `FM-08`). |
| **Failure mode** | `FM-05` (`pre_deducted`) dẫn tới `FM-08` (`misreport`) trong `docs/failure_taxonomy.md` |
| **Đối chứng (`fixed C-014@11`)** | Trên shape `fixed` cùng `C-014@11`, agent giữ nguyên `proposal=150000` từ **Step 3** (`quote`) để truyền vào `issue_refund`, host trừ `30000` đã hoàn trước đó và ghi đúng `ledger.refund_vnd=120000`, đồng thời **Step 4** (`reply`) báo đúng `120.000đ` khớp với ledger. |
| **Regression test** | `tests/test_lab9_graders.py::test_wrong_amount_in_ledger` và `tests/test_lab9_graders.py::test_reply_ledger_mismatch_caught` (`RefundAmountCorrect` bắt `ledger=90000 != 120000`; `ReplyLedgerMatch` bắt `reply=120.000đ != ledger=90000`). |
| **Chưa chắc chắn** | Nếu chỉ đọc `reply` (*"đã hoàn 120.000đ"*), câu trả lời trùng khớp hoàn toàn với con số mong đợi của khách (`120.000đ`), nên một LLM judge chỉ chấm văn bản (như `judge_helpful`) sẽ chấm `PASS` dù khách bị thiệt `30.000đ` trong DB. |
