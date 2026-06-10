#!/bin/bash
#SBATCH --job-name=pii_eval_suite
#SBATCH --partition=batch
#SBATCH --gres=gpu:rtx6000:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=/data1/mk04/pii_ner/logs/slurm_%j.out
# 평가 스위트 (단독 seqeval + 룰/ML단독/하이브리드/유니온 채점) — MODEL 인자.
# venv staging 은 train_ner.sbatch 와 동일 방식.

set -e
PROJ=/data1/mk04/pii_ner
TGZ=$PROJ/ner_env.tgz
WORK=/tmp/pii_suite_${SLURM_JOB_ID}
VENV=$WORK/ner_env
MODEL=${MODEL:?MODEL 디렉토리 또는 base-fuzzy 를 지정하세요}

mkdir -p "$PROJ/logs" "$WORK"
export HF_HOME=/data1/mk04/.cache/huggingface
export TOKENIZERS_PARALLELISM=false
export PATH=/usr/local/bin:$PATH
trap 'rm -rf "$WORK"' EXIT

echo "[1/4] node=$(hostname) · venv staging → $VENV"
tar -I 'pigz -d' -xf "$TGZ" -C "$WORK" 2>/dev/null || tar -xzf "$TGZ" -C "$WORK"

echo "[2/4] python 3.12 (uv) 재배선"
uv python install 3.12 >/dev/null 2>&1 || true
PY=$(uv python find 3.12 2>/dev/null || true)
[ -x "$PY" ] || PY=$(command -v python3.12 || true)
[ -x "$PY" ] || { echo "FATAL python3.12"; exit 1; }
ln -sf "$PY" "$VENV/bin/python3.12"; ln -sf python3.12 "$VENV/bin/python"; ln -sf python3.12 "$VENV/bin/python3"
sed -i "s|^home = .*|home = $(dirname "$PY")|" "$VENV/pyvenv.cfg" 2>/dev/null || true

echo "[3/4] CUDA LD 경로"
SITE=$VENV/lib/python3.12/site-packages
export LD_LIBRARY_PATH="$(ls -d $SITE/nvidia/*/lib 2>/dev/null | tr '\n' ':')${LD_LIBRARY_PATH}"

echo "[4/4] 평가 스위트 — MODEL=$MODEL"
cd /data1/mk04/projects/ko-pii
"$VENV/bin/python" -u "$PROJ/scripts/eval_suite.py" "$MODEL"
