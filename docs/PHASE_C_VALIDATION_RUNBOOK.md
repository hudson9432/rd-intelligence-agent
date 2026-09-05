# Phase C 驗證執行手冊

這份文件只定義目前分支需要執行的驗證，不要求在驗證期間修改功能。
目標是讓接手者能分開確認：固定案例的正反判定、完整 A→B→C→D
流程，以及 Gemini 真實模型在相同流程中的行為。

## 驗證範圍

本輪需要回答五個問題：

1. 正方與反方來源能否同時進入 Phase C，而不是只保留支持資料。
2. 同一個核心 claim 能否被判為 `contested`。
3. 可由小型實驗解決的反論，是否成為 `poc_testable`，而不是直接扣成
   不可行。
4. 每個重要質疑是否都映射到一個 `ActionPlan` task。
5. 換成 Gemini 後，工作流是否能在有限 re-search 次數內結束，且不再因
   Critic 總是提供 `suggested_query` 而永遠到不了 PoC。

不要把「一定要得到 `ready_for_poc`」當成所有題目的通過條件。真實來源
可能合理地得到 `no_viable_direction`；真正的通過條件是它必須有可稽核的
證據與 claim 判定，而且只能在 re-search 預算耗盡並執行 viability gate
之後才得出該結論。

## 0. 準備

從 repository root 執行。Windows PowerShell：

```powershell
git switch feat/adversarial-research-pools
git pull --ff-only

py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item backend\.env.example backend\.env -ErrorAction SilentlyContinue
```

若已有 `.venv` 與 `backend/.env`，不需重建或覆寫。任何 API key 只放在
本機 `backend/.env`，不可貼進 issue、測試輸出或 commit。

## 1. 先跑固定的電商正反案例

這是最快且最重要的 Phase C 回歸測試。它使用四篇已從 arXiv 擷取的真實
來源，但不呼叫網路或 LLM，因此結果固定。

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest tests\test_ecommerce_contested_scenario.py -vv
Set-Location ..
```

預期：`2 passed`。案例應證明：

- 正方來源 2 篇、反方來源 2 篇。
- 核心 claim 的 `verdict` 是 `contested`。
- `resolution_status` 是 `poc_testable`。
- `derive_evidence_strength(...)` 是 5/5；可測試反論不直接降低此分數。
- 兩個重要質疑都各自映射到 `ActionPlan` 的 `question-1`、`question-2`。

測試題目與完整正反論點在
`demo/fixtures/ecommerce_recommender_scenario.json`。來源原始回應在
`demo/fixtures/ecommerce_recommender_pro_con_arxiv_response.xml`。

## 2. 跑 Phase C 與完整 backend 回歸

先跑此次變更直接影響的測試：

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest `
  tests\test_analysis_stage.py `
  tests\test_phase_c_analysis.py `
  tests\test_viability_gate.py `
  tests\test_fabricated_reference_tolerance.py `
  tests\test_opportunity_scoring.py `
  tests\test_action_agent.py `
  tests\test_ecommerce_contested_scenario.py -q
```

再跑格式、lint 與完整測試：

```powershell
..\.venv\Scripts\python.exe -m ruff format --check .
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m pytest
Set-Location ..
```

目前基準是 `284 passed`。Provider request pacing 會在短暫提早喚醒時重新
檢查 deadline；同一 clock tick 的 AgentEvent timestamp 也會保持單調遞增。
若這兩項仍失敗，應保留測試輸出並視為回歸，不再列為可忽略的 Windows
偶發問題。

## 3. 啟動 API 並跑全 mock mission

確認 `backend/.env` 保持：

```dotenv
MOCK_LLM=true
MOCK_EXTERNAL_APIS=true
```

啟動 backend：

```powershell
Set-Location backend
..\.venv\Scripts\uvicorn.exe app.main:app --port 8000
```

另開 PowerShell：

```powershell
$artifactDir = Join-Path $env:TEMP "rd-intelligence-phase-c"
New-Item -ItemType Directory -Force $artifactDir | Out-Null

$body = @{
  title = "RAG evidence audit"
  goal = "Assess whether an evidence-grounded RAG evaluation assistant is viable as a bounded PoC, including failure modes and contradictory evidence."
} | ConvertTo-Json

$mission = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/missions `
  -ContentType application/json `
  -Body $body

$result = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/missions/$($mission.id)/run"

$result | ConvertTo-Json -Depth 30 |
  Set-Content (Join-Path $artifactDir "mock-mission-result.json")
Invoke-RestMethod "http://localhost:8000/missions/$($mission.id)/events" |
  ConvertTo-Json -Depth 30 |
  Set-Content (Join-Path $artifactDir "mock-mission-events.json")
```

檢查 `%TEMP%/rd-intelligence-phase-c/mock-mission-result.json`：

- `status` 是 `completed`，而不是 provider 或 contract failure。
- `query_history` 包含一般查詢，也包含 failure、limitation、negative result
  或 contradictory evidence 類型的首輪反向查詢。
- `evidence_count` 大於 0。
- `iterations_used` 不超過設定的 `max_iterations`。
- 若 `handoff_status=ready_for_poc`，每個 candidate 都有 evidence IDs、
  claim assessments、verdict、resolution status 與 unresolved questions。
- 若有 `action_plan`，所有 `question-*` 都能在 task 的 `addresses` 找到。

## 4. 用 Gemini 跑固定來源

這一步只替換推理模型，保留固定 arXiv/GitHub 回應，最適合定位「mock 與
真實模型行為不同」的問題。在本機 `backend/.env` 設定：

```dotenv
MOCK_LLM=false
MOCK_EXTERNAL_APIS=true
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL=gemini-3.1-flash-lite
LLM_API_KEY=你的本機金鑰
LLM_MIN_REQUEST_INTERVAL_SECONDS=4.2
LLM_REQUEST_TIMEOUT_SECONDS=120
LLM_MAX_OUTPUT_TOKENS=8192
```

重啟 backend，使用非同步 endpoint。回應中的 `result_url` 可在完成後取得
包含 `ActionPlan.tasks_json` 與 Phase C audit 的完整結果：

```powershell
$artifactDir = Join-Path $env:TEMP "rd-intelligence-phase-c"
New-Item -ItemType Directory -Force $artifactDir | Out-Null

$body = @{
  title = "Gemini RAG evidence audit"
  goal = "Assess whether an evidence-grounded RAG evaluation assistant is viable as a bounded PoC, including failure modes and contradictory evidence."
} | ConvertTo-Json

$mission = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/missions `
  -ContentType application/json `
  -Body $body

$mission.id

$accepted = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/missions/$($mission.id)/run/async"
$accepted | ConvertTo-Json -Depth 10
```

每 10–20 秒輪詢；不要再次送出 `/run` 或 `/run/async`：

```powershell
$missionId = "把上一個視窗顯示的 mission id 貼在這裡"

Invoke-RestMethod "http://localhost:8000/missions/$missionId" |
  ConvertTo-Json -Depth 10

$events = Invoke-RestMethod "http://localhost:8000/missions/$missionId/events"
$events | ConvertTo-Json -Depth 30 |
  Set-Content (Join-Path $env:TEMP "rd-intelligence-phase-c\gemini-fixed-events.json")

$result = Invoke-RestMethod "http://localhost:8000/missions/$missionId/result"
$result | ConvertTo-Json -Depth 30 |
  Set-Content (Join-Path $env:TEMP "rd-intelligence-phase-c\gemini-fixed-result.json")
```

直到 mission status 為 `completed` 或 `failed`。完成後，最後一個
`workflow_completed` event 的 `metadata` 與 result endpoint 的完整結果
是本次主要報告資料，應保存為測試 artifact。需要特別檢查：

- 不因模型產生未知 evidence ID 而讓整個 mission 崩潰；無效項目應被丟棄，
  其他有效成果保留。
- `review_claims` 的成果確實進入 `claim_assessments`，而不是被 Critic 狀態
  提前短路後丟棄。
- 到達 re-search 上限後仍會執行 viability gate。
- `suggested_query` 的存在不應單獨等同「沒有可行方向」。
- `contested + poc_testable` 可以成為 PoC；`refuted + fatal` 不可成為 PoC。

## 5. 用 Gemini 與真實來源跑電商題目

只有前四節通過後才跑。將本機 `backend/.env` 改為：

```dotenv
MOCK_LLM=false
MOCK_EXTERNAL_APIS=false
```

保留上一節的 Gemini 設定。若有 GitHub token，可在本機設定
`GITHUB_TOKEN`；沒有也能跑，但更容易碰到搜尋額度。重啟 backend 後建立，
並使用非同步 endpoint：

```powershell
$artifactDir = Join-Path $env:TEMP "rd-intelligence-phase-c"
New-Item -ItemType Directory -Force $artifactDir | Out-Null

$body = @{
  title = "E-commerce extension audit"
  goal = "Assess viable extensions for an e-commerce platform. For every proposed direction, compare quantified supporting and opposing evidence, identify uncontrolled variables and baseline risks, and propose a bounded PoC with measurable pass/fail criteria."
} | ConvertTo-Json

$mission = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/missions `
  -ContentType application/json `
  -Body $body

$mission.id

$accepted = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/missions/$($mission.id)/run/async"
$accepted | ConvertTo-Json -Depth 10
```

使用上一節的輪詢方式保存 events，完成後從 `result_url` 取得結果並保存為
`gemini-live-ecommerce-result.json`。這是探索性真實資料測試，因此不要求
方向名稱一定是「個人化推薦」，但報告至少要列出：

```powershell
$result = Invoke-RestMethod "http://localhost:8000/missions/$missionId/result"
$result | ConvertTo-Json -Depth 30 |
  Set-Content (Join-Path $env:TEMP "rd-intelligence-phase-c\gemini-live-ecommerce-result.json")
```

- A 階段每輪 queries、實際抓到的 source 數量與來源失敗。
- B 階段每輪 extracted evidence 數量與累計數量。
- C 階段提出的方向、每個 claim 的 supporting/opposing evidence IDs、
  `support_strength`、`counterevidence_strength`、`verdict`、
  `resolution_status` 與 `poc_testability`。
- re-search 查詢、執行輪數，以及最後停止原因。
- 被選 PoC、未解問題、每個問題對應的 ActionPlan task 與 pass/fail 指標。
- 被丟棄或無法套用的 LLM 產物；不得將未知 ID 當成有效證據。

## 通過／失敗判準

整體判為通過需同時符合：

- 所有固定測試通過。
- full mock mission 能終止且不呼叫外部服務。
- Gemini 固定來源 mission 能終止，沒有無限 re-search。
- 真實資料 mission 不超過研究輪數與查詢上限。
- 每個事實性 claim 都保留有效 evidence ID；未知欄位沒有被猜測。
- 反論能被區分為 `poc_testable`、`research_gap` 或 `fatal`。
- 所有重要且可測的反論都有 ActionPlan task；無法解決的核心 fatal objection
  不得被包裝成 PoC。

下列任一情況判為失敗：

- 有 29 份或其他非零 evidence，卻因 Critic 每題都有 `suggested_query` 而從未
  執行 claim viability 判定。
- 一個模型捏造的 UUID 讓整個 mission 失敗。
- re-search 預算已用完仍繼續搜尋。
- `contested` 一律被當成扣分或不可行，而不檢查它是否能由 PoC 解決。
- ActionPlan 遺漏任何 retained `question-*`。

## 目前已知的觀測限制

`GET /missions/{id}/result` 現在可看到完整 evidence、support/challenge/excluded
分類、PoC candidate、claim 的正反 evidence IDs、verdict、resolution status、
unresolved questions 與 ActionPlan。

仍未保存的是生成後遭淘汰的所有 Critic candidate questions，以及無法套用的
LLM 原始輸出。這些項目目前只能由單元測試驗證丟棄規則，不能從完成後的
mission result 重建；若產品需要逐項 model-output 稽核，必須另訂安全的事件
contract，且不得把 prompt、API key 或未驗證的來源內容直接寫進 log。
