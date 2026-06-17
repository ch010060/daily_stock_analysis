# 雲伺服器 Web 介面訪問指南

> Route B server-safe profile 當前不建議在本 phase 開啟公開監聽。
> 僅支援本機迴環繫結（127.0.0.1）；如需公網可見，屬於另一個專門部署檔（未在本 PR 內開啟）。

如果你已經把專案部署到雲伺服器，但不知道在瀏覽器裡輸入什麼地址才能開啟 Web 管理介面，這篇教程就是為你準備的。

> 其實就兩步：讓服務監聽外網，再在瀏覽器裡輸入地址。

---

## 目錄

- [方式一：直接部署（pip + python）](#方式一直接部署pip--python)
- [方式二：Docker Compose](#方式二docker-compose)
- [如何在瀏覽器裡開啟介面](#如何在瀏覽器裡開啟介面)
- [如何確認 Docker 重建已生效](#如何確認-docker-重建已生效)
- [訪問不了？先檢查這幾項](#訪問不了先檢查這幾項)
- [可選：Nginx 反向代理（繫結域名 / 80 埠）](#可選nginx-反向代理繫結域名--80-埠)
- [安全建議](#安全建議)

---

## 方式一：直接部署（pip + python）

### 第一步：修改 .env 中的監聽地址

用編輯器開啟 `.env`（在專案根目錄，即包含 `main.py` 的目錄），找到這一行：

```env
WEBUI_HOST=127.0.0.1
```

`127.0.0.1` 為本機迴環繫結，保持該配置。

> Route B 在當前 gate 修訂下預設走本機安全模式，`0.0.0.0` 公網監聽會觸發本地安全閘道拒絕。

### 第二步：啟動服務

在專案根目錄執行：

```bash
# 只啟動 Web 介面（不自動執行分析）
python main.py --webui-only

# 或者：啟動 Web 介面（啟動時執行一次分析；需每日定時分析請加 --schedule 或設 SCHEDULE_ENABLED=true）
python main.py --webui
```

啟動成功後，終端會輸出類似：

```
FastAPI 服務已啟動: http://127.0.0.1:8000
```

如果你想讓服務在退出終端後繼續執行，可以用 `nohup`：

```bash
nohup python main.py --webui-only > /dev/null 2>&1 &
```

> 日誌檔案會由程式自動寫入 `logs/` 目錄，用 `tail -f logs/stock_analysis_*.log` 檢視。

### 修改埠（可選）

預設埠是 8000。如果想改用其他埠，在 `.env` 裡設定：

```env
WEBUI_PORT=8888
```

然後重啟服務。

---

## 方式二：Docker Compose

### 第一步：確認已有 .env 配置

專案的 `docker/docker-compose.yml` 在容器內部保持 `WEBUI_HOST=127.0.0.1`。

### 第二步：啟動服務

在專案根目錄執行：

```bash
# 同時啟動定時分析 + Web 介面（推薦）
docker-compose -f ./docker/docker-compose.yml up -d

# 或者只啟動 Web 介面服務
docker-compose -f ./docker/docker-compose.yml up -d server
```

啟動後檢視狀態：

```bash
docker-compose -f ./docker/docker-compose.yml ps
```

看到 `server` 服務狀態為 `running` 就說明 Web 介面已經在執行了。

### 修改埠（可選）

預設埠是 8000。如果想改用其他埠，在 `.env` 裡設定：

```env
API_PORT=8888
```

然後重新啟動容器：

```bash
docker-compose -f ./docker/docker-compose.yml down
docker-compose -f ./docker/docker-compose.yml up -d
```

---

## 如何在瀏覽器裡開啟介面

服務啟動後，在瀏覽器位址列輸入：

```
http://你的伺服器公網IP:8000
```

例如，如果你的伺服器 IP 是 `1.2.3.4`，就輸入：

```
http://1.2.3.4:8000
```

如果你的域名已經解析到這臺伺服器，也可以直接用域名訪問：

```
http://your-domain.com:8000
```

> **在哪裡查公網 IP？** 登入你的雲伺服器控制檯（阿里雲/騰訊雲/AWS 等），在例項列表裡可以看到「公網 IP」或「彈性 IP」。

---

## 如何確認 Docker 重建已生效

先區分兩件事：

1. **Docker 映象釋出版本**：看你部署時使用的映象 tag，例如 `ghcr.io/zhulinsen/daily_stock_analysis:v3.12.0`。倉庫的 Docker 釋出由 `.github/workflows/docker-publish.yml` 按 `v*.*.*` Git tag 觸發，所以 Docker 版本應以映象 tag / GitHub Releases 為準。
2. **當前頁面載入的前端構建**：看 WebUI “系統設定”頁裡的版本資訊卡片，用來確認瀏覽器拿到的靜態資源是否已經更新。

也就是說，**“系統設定”裡的版本資訊更適合判斷前端是否重建成功，不等同於 Docker 映象釋出版本**。

WebUI 現在會在“系統設定”頁展示只讀的“版本資訊”卡片，包含：

- `WebUI 版本`
- `構建標識`
- `構建時間`

如果 `apps/dsa-web/package.json` 裡的版本號仍是佔位值 `0.0.0`，頁面會自動回退展示本次前端構建生成的 `構建標識`，避免你誤把佔位版本當成真實發布版本。

當你重新執行 `docker-compose -f ./docker/docker-compose.yml up -d --build`，或者單獨重新執行前端 `npm run build` 後，可以重新整理瀏覽器並進入“系統設定”，優先確認“構建時間”是否已經變化；若變化，通常就說明當前載入的靜態資源已經切換到最新構建。

如果你想確認“我現在到底部署的是哪個正式版本”，優先用下面這些方式：

```yaml
# 方式 1：看 docker-compose / 部署指令碼里的 image tag
image: ghcr.io/zhulinsen/daily_stock_analysis:v3.12.0
```

```bash
# 方式 2：回看你的拉取命令
docker pull ghcr.io/zhulinsen/daily_stock_analysis:v3.12.0
```

如果你一直使用 `latest`，建議改成顯式版本 tag；否則很難僅憑容器內頁面資訊判斷自己是否已經重複更新到同一版本。

在確認本地前端打包鏈路時，建議執行以下命令作為最小驗證閉環：

```bash
cd apps/dsa-web
npm ci
npm run lint
npm run build
```

其中 `build` 成功後，`static` 下生成的 `index.html`/JS/CSS 資源會包含本次構建時間與構建版本資訊；重新整理後在“版本資訊”卡片中應能見到變化。

---

## 訪問不了？先檢查這幾項

### 1. 安全組 / 防火牆沒有放行埠

這是最常見的原因。雲伺服器預設只開放 22（SSH）埠，需要手動放行 8000（或你改的埠）。

**操作方法**（以阿里云為例）：
1. 登入阿里雲控制檯 → 雲伺服器 ECS → 找到你的例項
2. 點選「安全組」→「配置規則」→「新增安全組規則」
3. 方向選「入方向」，埠範圍填 `8000/8000`，授權物件按你的網路邊界策略配置（當前文件不支援 Route B 的公網監聽）。

騰訊雲、AWS 等雲廠商操作類似，找到「安全組」或「防火牆規則」，新增一條允許 TCP 8000 埠的入站規則即可。

### 2. 伺服器系統防火牆攔截了

如果你的系統開啟了 `ufw` 或 `firewalld`，也需要放行埠：

```bash
# Ubuntu / Debian（ufw）
sudo ufw allow 8000

# CentOS / RHEL（firewalld）
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### 3. 直接部署時 .env 裡的 WEBUI_HOST 沒改

這是第二常見原因。`.env` 裡預設是 `WEBUI_HOST=127.0.0.1`，這樣服務只監聽本機。

在 Route B server-safe profile 下這是預期行為；如需變更為公開監聽，請走“公開部署”專用配置。

> Docker 方式不需要改這個，可以跳過。

### 4. 埠號對不上

檢查訪問地址裡的埠是否和 `.env` / 啟動命令裡設定的埠一致。

- 直接部署：預設 8000，可透過 `WEBUI_PORT=xxxx` 修改
- Docker：預設 8000，可透過 `API_PORT=xxxx` 修改

### 5. 頁面能開啟，但 UI 元素異常變大 / 佈局錯亂

**症狀**：瀏覽器能訪問到 8000 埠，頁面有內容，但文字、按鈕、卡片尺寸異常大，沒有正常佈局與配色。

**根因**：`static/index.html` 存在但 CSS/JS 資源缺失（`static/assets/` 為空或不存在），瀏覽器載入了 HTML 框架但無法拿到樣式與指令碼，退化為裸 HTML 渲染。

可先用瀏覽器開發者工具（F12 → Network 標籤頁）檢查是否有 `/assets/index-*.js`、`/assets/index-*.css` 的 **404** 錯誤。若有，按以下方式修復：

**Docker 使用者**：

```bash
docker-compose -f ./docker/docker-compose.yml down
docker-compose -f ./docker/docker-compose.yml build --no-cache
docker-compose -f ./docker/docker-compose.yml up -d
```

重建完成後，用 `Ctrl+Shift+R` 強制重新整理瀏覽器快取，再訪問頁面。

**直接部署使用者**：先確保已安裝 Node.js 18+（推薦 20+），然後手動構建前端：

```bash
cd apps/dsa-web
npm ci
npm run build
cd ../..
python main.py --webui-only
```

---

## 可選：Nginx 反向代理（繫結域名 / 80 埠）

如果你有域名，或者不想在地址裡帶 `:8000`，可以用 Nginx 做反向代理，把 80/443 埠流量轉發給後端服務。

### 安裝 Nginx

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y nginx

# CentOS
sudo yum install -y nginx
```

### 配置檔案示例

新建檔案 `/etc/nginx/conf.d/stock-analyzer.conf`，內容如下（把 `your-domain.com` 改成你的域名或 IP）：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 支援 WebSocket（Agent 對話頁面需要）
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 啟用配置並重啟 Nginx

```bash
sudo nginx -t            # 檢查配置有沒有語法錯誤
sudo systemctl reload nginx
```

配置成功後，直接用 `http://your-domain.com` 訪問即可，不需要帶埠號。

> **使用 Nginx 後的注意事項**：
> - 如果你開啟了 Web 登入認證（`ADMIN_AUTH_ENABLED=true`），建議在 `.env` 中把 `TRUST_X_FORWARDED_FOR=true` 一併開啟，否則系統可能無法正確識別真實 IP。該選項適用於**單層可信反向代理**（Nginx → App）部署；如果使用多級代理或 CDN（CDN → Nginx → App），登入限流的 key 可能退化為邊緣代理 IP 而非真實客戶端 IP，需根據實際拓撲評估。
> - 如需 HTTPS，可以用 [Certbot](https://certbot.eff.org/) 自動申請免費的 Let's Encrypt 證書。

---

## 安全建議

把 Web 介面暴露到公網之前，強烈建議開啟登入密碼保護：

在 `.env` 中設定：

```env
ADMIN_AUTH_ENABLED=true
```

重啟服務後，第一次訪問網頁時會要求設定初始密碼。設定完成後，每次開啟設定頁面都需要輸入密碼，可以防止 API Key 等敏感配置被他人看到。

> 如果忘了密碼，可以在伺服器上執行：`python -m src.auth reset_password`

---

遇到其他問題？歡迎 [提交 Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)。
