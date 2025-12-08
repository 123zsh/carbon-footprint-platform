#!/bin/bash
# 强制安装Python 3.9
echo "正在强制使用Python 3.9..."
python3.9 -m pip install --upgrade pip
python3.9 -m pip install -r requirements.txt