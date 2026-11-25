# ringecho-lang.org/dist 部署预设

这是 `rvm` 消费的稳定分发入口，默认形态为 **Cloudflare Worker 302**：不复制
发布资产，只把稳定 URL 映射到 GitHub Release 资产，并把 `index.txt` 从
GitHub Releases API 生成（缓存 5 分钟）。

```
GET /dist/index.txt              已发布版本，每行一个
GET /dist/v<版本>/<资产>          302 到 GitHub Release 同名资产
```

资产名在跳转前会用白名单正则校验，因此该端点不会变成开放重定向。

## 部署步骤（需要你的 Cloudflare 凭据，本仓库不存放）

1. 安装/调用 wrangler（无需全局安装）：
   ```sh
   npx --yes wrangler@4 --version
   ```
2. 在 Cloudflare 创建 API Token，权限至少包含：
   - `Workers Scripts: Edit`
   - `Zone: Workers Routes: Edit`（限定 `ringecho-lang.org`）
3. 本地部署（或配置 GitHub Secret `CLOUDFLARE_API_TOKEN` 后手动触发
   `.github/workflows/site.yml`）：
   ```sh
   cd deploy/site
   CLOUDFLARE_API_TOKEN=... npx --yes wrangler@4 deploy
   ```
4. DNS：Workers Route 需要一个**已代理**的 DNS 记录才能命中。
   当前 `ringecho-lang.org` 只有 NS，没有 A/AAAA。二选一：
   - 给根域加一条代理的占位记录：`AAAA 100::`（或 `A 192.0.2.1`），仅用于让
     Cloudflare 接管该主机名；
   - 或把 route 改成 `dist.ringecho-lang.org/*`，并给该子域加代理记录
     （同时把 `rvm` 的 `RVM_SITE_BASE` 改为 `https://dist.ringecho-lang.org`）。
5. 验证：
   ```sh
   curl -fsSL https://ringecho-lang.org/dist/index.txt
   curl -sI https://ringecho-lang.org/dist/v0.4.0/ringecho-0.3.0-windows-x64.zip
   curl -s -o /dev/null -w '%{http_code}\n' \
     https://ringecho-lang.org/dist/v0.4.0/../../etc/passwd   # 期望 404
   ```

## 后续切到自托管资产（可选）

若要摆脱 GitHub 依赖，把资产上传到 R2（或任何静态源），在 Worker 里把
`RELEASE_BASE` 换成自己的基地址即可；`index.txt` 可以改为读取 R2 的对象清单，
或在发布流程里生成后一起上传。`rvm` 侧无需改动。

## 边界

- 本目录只有 Worker 代码与部署说明；**不包含任何密钥**，也不在 CI 中自动部署
  （仅 `workflow_dispatch` 手动触发）。
- 站点未上线时 `rvm install` 仍会回退 GitHub Releases，用户不会被完全阻断。
