"""Frozen icon enum from PLAN.md — single source of truth. Do not add/remove without updating PLAN.md."""
from enum import Enum


class IconID(str, Enum):
    REPEAT = "REPEAT"
    IDEA = "IDEA"
    BUILD = "BUILD"
    HELP = "HELP"
    AGREE = "AGREE"
    DISAGREE = "DISAGREE"
    QUESTION = "QUESTION"
    STOP = "STOP"
    CHECK = "CHECK"
    DONE = "DONE"


class QuickReplyID(str, Enum):
    DONE = "DONE"
    NEED_HELP = "NEED_HELP"


PLEASE_REPEAT = "PLEASE_REPEAT"

ICON_IDS = {member.value for member in IconID}
QUICK_REPLY_IDS = {member.value for member in QuickReplyID}
