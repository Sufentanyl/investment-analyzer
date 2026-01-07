#!/usr/bin/expect -f
set timeout 30
spawn ssh -o StrictHostKeyChecking=no root@104.129.11.185 "cd ~/investment-analyzer && docker logs --tail 100 investment-analyzer 2>&1 | grep -E '正在邀请|Gemini|API|分析'"
expect {
    "password:" {
        send "jyb10291225\r"
        interact
    }
}
