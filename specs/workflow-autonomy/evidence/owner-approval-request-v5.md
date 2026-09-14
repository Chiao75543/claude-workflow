# workflow-autonomy v5 Owner 核准請求

請 Owner 對 `specs/workflow-autonomy/spec.yaml` draft version 5 做明確決定。

建議核准以下兩項程序性信任邊界：

1. **Owner approval anchor**：接受 core 驗證 `spec.approved.yaml`、`spec.hash`、`approval.json`、
   Git storage/tree 與 `source_ref` 的一致性，但不宣稱 repository 腳本能證明 `source_ref` 背後的
   平台使用者身分。若不接受，本版停止，另開規格定義 signature bytes、algorithm、key id 與 trust root。
2. **Independent reviewer anchor**：接受 core 驗證 writer/reviewer task ref 不同、completion ref、tree token、
   review token 與 test hashes 一致，但不宣稱 repository 腳本能證明 task ref 背後的平台身分。
   若不接受，本版停止，等待平台簽章身分介面。

建議的明確回覆為：

> 核准 workflow-autonomy v5，並接受上述兩項程序性 assurance gap；可進入 RED、freeze 與實作，
> 驗證通過後可 commit、push、開 PR 並 review，但不得 merge。

在收到等價的明確核准前，不得建立 approved snapshot、RED、freeze、實作 commit、push 或 PR。
