#!/bin/bash
#SBATCH --job-name=pii_ner_train
#SBATCH --partition=batch
#SBATCH --gres=gpu:rtx6000:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --output=/data1/mk04/pii_ner/logs/slurm_%j.out
# 퍼지 PII NER 학습 (klue/roberta-large) — KDPII + 생성 행정데이터.
# venv 는 tarball(ner_env.tgz)로 staged → /tmp(노드 NVMe) 에 풀어 실행, python 3.12 uv 재배선.

set -e
PROJ=/data1/mk04/pii_ner
TGZ=$PROJ/ner_env.tgz
WORK=/tmp/pii_ner_${SLURM_JOB_ID}
VENV=$WORK/ner_env
BASE=${BASE:-klue/roberta-large}
OUT=${OUT:-$PROJ/out/klue_large_slurm}
EXTRA=${EXTRA:-}

mkdir -p "$PROJ/logs" "$WORK"
export HF_HOME=/data1/mk04/.cache/huggingface
export TOKENIZERS_PARALLELISM=false
export PATH=/usr/local/bin:$PATH
[ -f ~/.config/api_keys.env ] && source ~/.config/api_keys.env

echo "[1/4] node=$(hostname) · venv staging → $VENV"
tar -I 'pigz -d' -xf "$TGZ" -C "$WORK" 2>/dev/null || tar -xzf "$TGZ" -C "$WORK"

echo "[2/4] python 3.12 (uv) 재배선"
uv python install 3.12 >/dev/null 2>&1 || true
PY=$(uv python find 3.12 2>/dev/null || true)
[ -x "$PY" ] || PY=$(command -v python3.12 || true)
[ -x "$PY" ] || { echo "FATAL python3.12"; exit 1; }
ln -sf "$PY" "$VENV/bin/python3.12"; ln -sf python3.12 "$VENV/bin/python"; ln -sf python3.12 "$VENV/bin/python3"
sed -i "s|^home = .*|home = $(dirname "$PY")|" "$VENV/pyvenv.cfg" 2>/dev/null || true

echo "[3/4] CUDA LD 경로 + import 점검"
SITE=$VENV/lib/python3.12/site-packages
export LD_LIBRARY_PATH="$(ls -d $SITE/nvidia/*/lib 2>/dev/null | tr '\n' ':')${LD_LIBRARY_PATH}"
"$VENV/bin/python" -c "import torch,transformers,seqeval;print('  torch',torch.__version__,'cuda',torch.cuda.is_available())"

echo "[4/4] 학습 시작 — base=$BASE out=$OUT $EXTRA"
cd /data1/mk04/projects/ko-pii
exec "$VENV/bin/python" -u "$PROJ/scripts/train_ner.py" --base "$BASE" --out "$OUT" $EXTRA
