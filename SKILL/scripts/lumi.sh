#!/usr/bin/env bash
# lumi.sh — curl-based LumiCreate-Pro client (Bash + jq)
# 与 lumi.py 等价的轻量版，依赖 curl + jq
#
# 环境变量：
#   LUMI_API   默认 http://127.0.0.1:18520

set -euo pipefail

API="${LUMI_API:-http://127.0.0.1:18520}"

die()   { echo "$*" >&2; exit 1; }
need()  { command -v "$1" >/dev/null || die "缺少依赖: $1"; }
need curl
need jq

usage() {
  cat <<EOF
Usage:
  lumi.sh health
  lumi.sh projects list
  lumi.sh projects new <name> [folder]
  lumi.sh projects info <id>
  lumi.sh projects delete <id> --yes
  lumi.sh manuscript get <id>
  lumi.sh scenes get <id>
  lumi.sh characters get <id>
  lumi.sh images list <id>
  lumi.sh video workflows
  lumi.sh video merge <id>
  lumi.sh subtitle status <id>
  lumi.sh subtitle script <id>
  lumi.sh subtitle generate-srt <id> [fps=24] [model=base]
  lumi.sh subtitle embed <id> [font="等线 Bold"] [size=18]
  lumi.sh audio ms-tts <text> [voice=zh-CN-XiaoxiaoNeural] [rate=+0%] <out.mp3>
  lumi.sh settings get
EOF
  exit 1
}

# ── SSE consumer：把 \"data: ...\" 行解析成 JSON 输出到 stdout ────────────────
sse_consume() {
  while IFS= read -r line; do
    case "$line" in
      "data: [DONE]") return 0 ;;
      "data: "*)      printf '%s\n' "${line#data: }" ;;
    esac
  done
}

cmd="${1:-}"; shift || usage
case "$cmd" in
  health)
    curl -fsSL "$API/api/health" | jq .
    ;;

  projects)
    sub="${1:-}"; shift || usage
    case "$sub" in
      list)
        curl -fsSL "$API/api/projects" | jq -r '.[] | "\(.id)  \(.progress)  \(.name)"'
        ;;
      new)
        name="${1:?name required}"; folder="${2:-default}"
        curl -fsSL -X POST "$API/api/projects" \
             -H 'Content-Type: application/json' \
             -d "$(jq -n --arg n "$name" --arg f "$folder" '{name:$n, folder_id:$f}')" | jq .
        ;;
      info)
        curl -fsSL "$API/api/projects/${1:?id required}" | jq .
        ;;
      delete)
        id="${1:?id required}"; flag="${2:-}"
        [[ "$flag" == "--yes" ]] || die "DANGER: 加 --yes 才执行"
        curl -fsSL -X DELETE "$API/api/projects/$id" && echo "deleted $id"
        ;;
      *) usage ;;
    esac
    ;;

  manuscript)
    sub="${1:-}"; shift || usage
    case "$sub" in
      get)
        curl -fsSL "$API/api/projects/${1:?id required}/manuscript" | jq .
        ;;
      *) usage ;;
    esac
    ;;

  scenes)
    sub="${1:-}"; shift || usage
    case "$sub" in
      get) curl -fsSL "$API/api/projects/${1:?id required}/scenes" | jq . ;;
      *) usage ;;
    esac
    ;;

  characters)
    sub="${1:-}"; shift || usage
    case "$sub" in
      get) curl -fsSL "$API/api/projects/${1:?id required}/characters" | jq . ;;
      *) usage ;;
    esac
    ;;

  images)
    sub="${1:-}"; shift || usage
    case "$sub" in
      list) curl -fsSL "$API/api/projects/${1:?id required}/images" | jq . ;;
      *) usage ;;
    esac
    ;;

  video)
    sub="${1:-}"; shift || usage
    case "$sub" in
      workflows) curl -fsSL "$API/api/video-engine/workflows" | jq . ;;
      merge)
        id="${1:?id required}"
        scenes_json=$(curl -fsSL "$API/api/projects/$id/scenes")
        order=$(jq '[.scenes[].id]' <<<"$scenes_json")
        body=$(jq -n --arg id "$id" --argjson order "$order" '{project_id:$id, scene_order:$order}')
        curl -fsSL -X POST "$API/api/video-engine/merge-project-video" \
             -H 'Content-Type: application/json' -d "$body" | jq .
        ;;
      *) usage ;;
    esac
    ;;

  subtitle)
    sub="${1:-}"; shift || usage
    case "$sub" in
      status) curl -fsSL "$API/api/subtitle-engine/status/${1:?id required}" | jq . ;;
      script) curl -fsSL "$API/api/subtitle-engine/script/${1:?id required}" | jq . ;;
      generate-srt)
        id="${1:?id required}"; fps="${2:-24}"; model="${3:-base}"
        lines=$(curl -fsSL "$API/api/subtitle-engine/script/$id" | jq '.lines')
        body=$(jq -n --arg id "$id" --argjson lines "$lines" \
                       --argjson fps "$fps" --arg model "$model" \
                       '{project_id:$id, lines:$lines, fps:$fps,
                         manual_advance:0.0, model_name:$model}')
        curl -fsSL -N -X POST "$API/api/subtitle-engine/generate-srt" \
             -H 'Content-Type: application/json' -d "$body" \
          | sse_consume | jq -c .
        ;;
      embed)
        id="${1:?id required}"; font="${2:-等线 Bold}"; size="${3:-18}"
        body=$(jq -n --arg id "$id" --arg f "$font" --argjson s "$size" \
                       '{project_id:$id, font_name:$f, font_size:$s}')
        curl -fsSL -N -X POST "$API/api/subtitle-engine/embed" \
             -H 'Content-Type: application/json' -d "$body" \
          | sse_consume | jq -c .
        ;;
      *) usage ;;
    esac
    ;;

  audio)
    sub="${1:-}"; shift || usage
    case "$sub" in
      ms-tts)
        text="${1:?text required}"; out="${4:?out file required}"
        voice="${2:-zh-CN-XiaoxiaoNeural}"; rate="${3:-+0%}"
        body=$(jq -n --arg t "$text" --arg v "$voice" --arg r "$rate" \
                       '{text:$t, voice:$v, rate:$r}')
        resp=$(curl -fsSL -X POST "$API/api/audio-engine/ms-tts" \
                    -H 'Content-Type: application/json' -d "$body")
        jq -r '.data' <<<"$resp" | base64 -d > "$out"
        jq -r '"saved: " + "'$out'" + " (\(.duration_ms)ms, \(.format))"' <<<"$resp"
        ;;
      *) usage ;;
    esac
    ;;

  settings)
    sub="${1:-}"; shift || usage
    case "$sub" in
      get) curl -fsSL "$API/api/settings" | jq . ;;
      *) usage ;;
    esac
    ;;

  *) usage ;;
esac
