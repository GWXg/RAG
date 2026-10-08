当前结构大致是：

```txt
Claude Code 插件
  ↓
http://127.0.0.1:3000/v1/messages
  ↓
claude-deepseek-proxy.service
  ↓
https://assistant.cup.edu.cn/api/v1/chat/completions
  ↓
deepseek-ai/DeepSeek-V4-Flash
```

---

# 一、常用文件位置

一般会涉及 3 个文件。

## 1. 代理程序

```bash
~/claude-deepseek-proxy/proxy.py
```

作用：负责把 Claude Code 的 Anthropic 协议请求转换成 OpenAI-compatible 请求。

---

## 2. 代理环境变量文件

```bash
~/.config/claude-deepseek-proxy/env
```

作用：保存 DeepSeek 的 API 地址、API Key、模型名。

典型内容：

```bash
OPENAI_BASE_URL=https://assistant.cup.edu.cn/api/v1
OPENAI_API_KEY=你的原始key，不要加sk-
OPENAI_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

---

## 3. Claude Code 配置文件

```bash
~/.claude/settings.json
```

作用：告诉 Claude Code 插件去访问你的本地代理，而不是官方 Claude API。

典型内容：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:3000",
    "ANTHROPIC_AUTH_TOKEN": "dummy",
    "ANTHROPIC_API_KEY": "dummy",
    "ANTHROPIC_MODEL": "deepseek-ai/DeepSeek-V4-Flash",
    "ANTHROPIC_SMALL_FAST_MODEL": "deepseek-ai/DeepSeek-V4-Flash"
  }
}
```

---

# 二、查看代理是否正在运行

执行：

```bash
systemctl --user status claude-deepseek-proxy
```

如果看到：

```txt
active (running)
```

说明代理正在运行。

如果看到：

```txt
inactive
failed
```

说明代理没有运行或启动失败。

也可以用：

```bash
curl -sS http://127.0.0.1:3000/
```

正常应返回：

```json
{"ok":true}
```

---

# 三、启动代理

```bash
systemctl --user start claude-deepseek-proxy
```

启动后检查：

```bash
systemctl --user status claude-deepseek-proxy
```

---

# 四、停止代理

```bash
systemctl --user stop claude-deepseek-proxy
```

停止后，Claude Code 插件会无法连接，通常会报：

```txt
API Error: Unable to connect to API
ConnectionRefused
```

这是正常的，因为代理已经关闭。

---

# 五、重启代理

修改 API Key、模型名、代理代码后，都需要重启代理：

```bash
systemctl --user restart claude-deepseek-proxy
```

然后检查：

```bash
systemctl --user status claude-deepseek-proxy
```

---

# 六、设置开机自启

启用开机自启：

```bash
systemctl --user enable claude-deepseek-proxy
```

立即启动并启用自启：

```bash
systemctl --user enable --now claude-deepseek-proxy
```

如果服务器重启后你没有登录，用户级服务可能不会自动运行。建议启用 linger：

```bash
loginctl enable-linger $USER
```

检查是否启用：

```bash
loginctl show-user $USER | grep Linger
```

看到：

```txt
Linger=yes
```

说明已经启用。

---

# 七、关闭开机自启

如果以后不想让代理开机自动启动：

```bash
systemctl --user disable claude-deepseek-proxy
```

如果要同时停止当前正在运行的代理：

```bash
systemctl --user disable --now claude-deepseek-proxy
```

---

# 八、修改 API Key

不要改 `proxy.py`，只改环境变量文件。

执行：

```bash
nano ~/.config/claude-deepseek-proxy/env
```

把这一行：

```bash
OPENAI_API_KEY=旧key
```

改成：

```bash
OPENAI_API_KEY=新key
```

注意：你的平台 key 是原始 UUID 风格 key，**不要加 `sk-`**。

例如：

```bash
OPENAI_API_KEY=8b6a3401-da4b-0158-d79b-ca2ee648e58c
```

不要写成：

```bash
OPENAI_API_KEY=sk-8b6a3401-da4b-0158-d79b-ca2ee648e58c
```

保存后重启服务：

```bash
systemctl --user restart claude-deepseek-proxy
```

测试：

```bash
curl -sS -m 60 "http://127.0.0.1:3000/v1/messages" \
  -H "Authorization: Bearer dummy" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-ai/DeepSeek-V4-Flash",
    "max_tokens": 100,
    "messages": [
      {
        "role": "user",
        "content": "hello"
      }
    ]
  }'
```

---

# 九、修改 API Base URL

编辑环境变量文件：

```bash
nano ~/.config/claude-deepseek-proxy/env
```

修改：

```bash
OPENAI_BASE_URL=https://assistant.cup.edu.cn/api/v1
```

例如换成新的服务地址：

```bash
OPENAI_BASE_URL=https://new-api.example.com/v1
```

保存后：

```bash
systemctl --user restart claude-deepseek-proxy
```

测试：

```bash
curl -sS http://127.0.0.1:3000/
```

然后再测 `/v1/messages`。

---

# 十、修改模型名

编辑：

```bash
nano ~/.config/claude-deepseek-proxy/env
```

修改：

```bash
OPENAI_MODEL=deepseek-ai/DeepSeek-V4-Flash
```

例如：

```bash
OPENAI_MODEL=deepseek-ai/DeepSeek-V3
```

保存后重启：

```bash
systemctl --user restart claude-deepseek-proxy
```

同时建议把 Claude Code 的模型名也同步修改。

编辑：

```bash
nano ~/.claude/settings.json
```

修改：

```json
"ANTHROPIC_MODEL": "deepseek-ai/DeepSeek-V3",
"ANTHROPIC_SMALL_FAST_MODEL": "deepseek-ai/DeepSeek-V3"
```

然后重启 VS Code，或执行：

```txt
Developer: Reload Window
```

---

# 十一、查看代理日志

实时查看：

```bash
journalctl --user -u claude-deepseek-proxy -f
```

查看最近 100 行：

```bash
journalctl --user -u claude-deepseek-proxy -n 100
```

查看本次启动后的日志：

```bash
journalctl --user -u claude-deepseek-proxy -b
```

如果 Claude Code 插件报错，优先看这里。

---

# 十二、修改代理代码

编辑：

```bash
nano ~/claude-deepseek-proxy/proxy.py
```

修改后必须重启：

```bash
systemctl --user restart claude-deepseek-proxy
```

查看是否启动成功：

```bash
systemctl --user status claude-deepseek-proxy
```

如果启动失败，看日志：

```bash
journalctl --user -u claude-deepseek-proxy -n 100
```

---

# 十三、测试 DeepSeek 原始接口

如果怀疑学校 DeepSeek 接口本身有问题，直接测原始接口：

```bash
curl -sS -m 60 "https://assistant.cup.edu.cn/api/v1/chat/completions" \
  -H "Authorization: Bearer 你的原始key不要加sk-" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-ai/DeepSeek-V4-Flash",
    "messages": [
      {
        "role": "user",
        "content": "hello"
      }
    ],
    "max_tokens": 100,
    "stream": false
  }'
```

如果这里失败，说明问题在 DeepSeek 服务、API Key、网络或权限，不是 Claude Code 代理的问题。

---

# 十四、测试本地代理接口

如果原始接口正常，再测代理：

```bash
curl -sS -m 60 "http://127.0.0.1:3000/v1/messages" \
  -H "Authorization: Bearer dummy" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepseek-ai/DeepSeek-V4-Flash",
    "max_tokens": 100,
    "messages": [
      {
        "role": "user",
        "content": "hello"
      }
    ]
  }'
```

如果返回：

```json
{
  "content": [
    {
      "text": "Hello! How can I help you today?",
      "type": "text"
    }
  ],
  "role": "assistant",
  "type": "message"
}
```

说明代理正常。

---

# 十五、常见报错处理

## 1. `ConnectionRefused`

含义：Claude Code 找不到代理。

检查：

```bash
systemctl --user status claude-deepseek-proxy
curl -sS http://127.0.0.1:3000/
```

修复：

```bash
systemctl --user restart claude-deepseek-proxy
```

如果你是 VS Code Remote SSH，要确认插件和代理在同一台机器上。

---

## 2. `403 Forbidden`

含义：代理访问学校 DeepSeek 接口被拒绝。

检查：

```bash
journalctl --user -u claude-deepseek-proxy -n 100
```

常见原因：

```txt
API Key 错误
API Key 加了 sk-
学校接口限制来源
请求头被网关拦截
```

先直接测试原始接口，确认 key 可用。

---

## 3. `授权信息不存在`

通常是 API Key 写错，或者错误加了 `sk-`。

检查：

```bash
cat ~/.config/claude-deepseek-proxy/env
```

应该是：

```bash
OPENAI_API_KEY=原始key
```

不是：

```bash
OPENAI_API_KEY=sk-原始key
```

修改后：

```bash
systemctl --user restart claude-deepseek-proxy
```

---

## 4. `Address already in use`

含义：3000 端口已经被占用。

查看占用：

```bash
ss -lntp | grep 3000
```

如果是旧的代理进程，停止服务：

```bash
systemctl --user stop claude-deepseek-proxy
```

然后查 Python 进程：

```bash
ps aux | grep proxy.py
```

必要时结束旧进程：

```bash
pkill -f proxy.py
```

再启动：

```bash
systemctl --user start claude-deepseek-proxy
```

---

# 十六、完全卸载代理

停止并禁用服务：

```bash
systemctl --user disable --now claude-deepseek-proxy
```

删除 service 文件：

```bash
rm ~/.config/systemd/user/claude-deepseek-proxy.service
```

重载 systemd：

```bash
systemctl --user daemon-reload
```

删除代理目录：

```bash
rm -rf ~/claude-deepseek-proxy
```

删除环境变量文件：

```bash
rm -rf ~/.config/claude-deepseek-proxy
```

可选：删除 Claude Code 自定义配置：

```bash
rm ~/.claude/settings.json
```

---

# 十七、推荐日常维护流程

每次 Claude Code 插件不能用时，按这个顺序排查：

```bash
# 1. 看代理服务是否活着
systemctl --user status claude-deepseek-proxy

# 2. 看本地代理端口是否通
curl -sS http://127.0.0.1:3000/

# 3. 测试代理消息接口
curl -sS -m 60 "http://127.0.0.1:3000/v1/messages" \
  -H "Authorization: Bearer dummy" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-ai/DeepSeek-V4-Flash","max_tokens":100,"messages":[{"role":"user","content":"hello"}]}'

# 4. 看日志
journalctl --user -u claude-deepseek-proxy -n 100

# 5. 必要时重启
systemctl --user restart claude-deepseek-proxy
```

最常用的维护命令其实只有这几个：

```bash
systemctl --user status claude-deepseek-proxy
systemctl --user restart claude-deepseek-proxy
systemctl --user stop claude-deepseek-proxy
journalctl --user -u claude-deepseek-proxy -f
nano ~/.config/claude-deepseek-proxy/env
```
