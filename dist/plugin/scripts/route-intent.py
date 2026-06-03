#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""
为 workflowprogram-* 入口技能提供确定性的意图路由。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List

from lib.io_utils import write_json


ENTRY_SKILL_BY_INTENT = {
    "develop": "workflowprogram-develop",
    "audit": "workflowprogram-audit",
    "iterate": "workflowprogram-iterate",
    "validate": "workflowprogram-validate",
    "publish": "workflowprogram-publish",
}

INTENT_KEYWORDS = {
    "develop": [
        ("设计", 3),
        ("创建", 3),
        ("新建", 3),
        ("搭建", 2),
        ("develop", 3),
        ("workflow", 1),
        ("工作流", 1),
        ("生成", 2),
        ("修改", 3),
        ("更新", 3),
        ("调整", 3),
        ("扩展", 3),
        ("拆分", 3),
        ("删除", 2),
        ("应用", 3),
        ("落地", 3),
    ],
    "audit": [("审计", 4), ("盘点", 3), ("扫描", 2), ("audit", 4), ("review", 2), ("结构问题", 3), ("偏离", 2)],
    "iterate": [("迭代", 4), ("优化", 2), ("改进", 2), ("evolve", 3), ("iterate", 4), ("lessons", 3)],
    "validate": [("验证", 4), ("校验", 4), ("检查", 2), ("validate", 4), ("test", 2), ("合规", 3)],
    "publish": [
        ("发布", 4),
        ("插件市场", 4),
        ("marketplace", 4),
        ("plugin install", 4),
        ("plugin marketplace", 4),
        ("publish", 4),
        ("github", 2),
        ("安装给别人", 3),
    ],
}


def parse_args() -> argparse.Namespace:
    """解析确定性意图路由所需的命令行参数。"""
    parser = argparse.ArgumentParser(description="Route natural-language request to workflowprogram-* intent")
    parser.add_argument("--request", required=True, help="User request text")
    parser.add_argument("--target-root", default="", help="Target project path")
    parser.add_argument("--out", default="", help="Optional path to write route evidence JSON")
    parser.add_argument("--strict", action="store_true", help="Fail when intent cannot be determined confidently")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    return parser.parse_args()


def slash_intent(request: str) -> str | None:
    """优先识别显式 `/workflowprogram-*` 调用，而不是关键词推断。"""
    match = re.match(r"^\s*/(?:workflowprogram-cn:)?workflowprogram-(develop|audit|iterate|validate|publish)\b", request)
    if not match:
        return None
    return match.group(1)


def score_request(request: str) -> Dict[str, int]:
    """用一组带权重的关键词为请求打分。"""
    text = request.lower()
    scores: Dict[str, int] = {key: 0 for key in INTENT_KEYWORDS}
    for intent, tokens in INTENT_KEYWORDS.items():
        for token, weight in tokens:
            if token.lower() in text:
                scores[intent] += int(weight)
    return scores


def choose_intent(request: str) -> Dict[str, object]:
    """返回最终意图，以及用于判定的解释性元数据。"""
    slash = slash_intent(request)
    if slash:
        return {
            "intent": slash,
            "confidence": 1.0,
            "reason": "explicit-slash",
            "scores": {k: 0 for k in INTENT_KEYWORDS},
        }

    scores = score_request(request)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_intent, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    # 零分或并列最高分都表示路由器无法证明存在比默认 develop
    # 更强的匹配，因此要把“存在歧义”显式暴露给上游调用方。
    ambiguous = top_score == 0 or top_score == second_score
    confidence = 0.0 if top_score == 0 else min(0.95, 0.5 + 0.15 * top_score)

    if ambiguous:
        return {
            "intent": "develop",
            "confidence": confidence,
            "reason": "fallback-default",
            "scores": scores,
            "ambiguous": True,
        }

    return {
        "intent": top_intent,
        "confidence": confidence,
        "reason": "keyword-match",
        "scores": scores,
        "ambiguous": False,
    }


def detect_request_kind(request: str) -> str:
    """给 change-context 使用的非权威请求形态提示。"""

    text = request.lower()
    redesign_tokens = [
        "redesign",
        "重新设计",
        "重做",
        "重构",
        "整体替换",
        "替换整个",
        "推倒重来",
    ]
    modify_tokens = [
        "修改",
        "更新",
        "调整",
        "扩展",
        "拆分",
        "删除",
        "增加",
        "补充",
        "改成",
        "应用",
        "落地",
        "采纳",
    ]
    create_tokens = ["创建", "新建", "设计一个", "生成", "搭建", "build", "create"]
    proposal_tokens = ["建议", "方案", "优化建议", "改进建议", "lessons", "iterate"]

    if any(token in text for token in redesign_tokens):
        return "redesign_existing"
    if any(token in text for token in modify_tokens):
        return "modify_existing"
    if any(token in text for token in create_tokens):
        return "create_new"
    if any(token in text for token in proposal_tokens):
        return "proposal_only"
    return "unknown"


def main() -> int:
    """解析目标意图，并在需要时对歧义路由直接失败。"""
    args = parse_args()
    routed = choose_intent(args.request)
    intent = str(routed["intent"])
    entry_skill = ENTRY_SKILL_BY_INTENT[intent]

    strict_env = os.environ.get("WORKFLOWPROGRAM_STRICT_ROUTE", "").strip().lower() in {"1", "true", "yes"}
    strict_mode = bool(args.strict or strict_env)
    ambiguous = bool(routed.get("ambiguous", False))

    target_root = args.target_root.strip() or str(Path.cwd())
    result = {
        "intent": intent,
        "entry_skill": entry_skill,
        "confidence": routed["confidence"],
        "reason": routed["reason"],
        "scores": routed["scores"],
        "ambiguous": ambiguous,
        "request_kind": detect_request_kind(args.request),
        "strict_mode": strict_mode,
        "target_root": str(Path(target_root).resolve()),
        "request": args.request,
    }

    if args.out.strip():
        write_json(Path(args.out).resolve(), result)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"intent={intent} entry_skill={entry_skill} "
            f"confidence={routed['confidence']:.2f} reason={routed['reason']}"
        )

    # 严格模式会把“尽力猜测”升级成硬门禁；如果存在歧义，就停止而不是静默回退到 develop。
    if strict_mode and ambiguous:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
