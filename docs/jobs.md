# 后台任务（JobBackend）

抽帧、导出等长任务**必须**经 `JobService.enqueue`，禁止业务代码直接起线程或调 subprocess。

## P0：`JOB_BACKEND=pg`

- 配置：`JOB_BACKEND=pg`（默认）。
- 队列与状态：PostgreSQL `jobs` 表；消费者用 `FOR UPDATE SKIP LOCKED` 抢任务，并写 `locked_by` / `lease_until`。
- 部署：api 同容器内跑 poller（可不拆 worker）；**不用 Redis**。
- HTTP：`POST /api/v1/jobs` 立即返回 `job_id`；`GET /api/v1/jobs/{id}` 轮询。
- 失败：`status=failed` + `error_message`，并打 error 日志（含 `job_id` / `job_type`）。

## 日后：独立 worker（仍可用 pg）

1. 同一套 `handlers`；worker 进程/容器只跑 `PgJobBackend` 消费者。
2. api 仅 `enqueue`（INSERT pending）。
3. Compose 增加 `worker` 服务即可，不必先上 Redis。

## 可选：`JOB_BACKEND=redis`

队列压力或已有 Redis 基建时再实现 `RedisQueueJobBackend`；**状态仍以 `jobs` 表为准**，业务代码不改。
