"""Project tracking: mirror the Notion task board into ClickUp and monday.com.

Notion ("Algo Trading -- Command Centre") is the source of truth. Claude chats
update it, and the two mirrors, through their connectors as work happens; these
scripts are the bulk catch-up for when a connector's daily allowance runs out or
a mirror has drifted.

    python -m boards.clickup_sync check | sync [--dry-run]
    python -m boards.monday_sync  check | sync [--dry-run] [--tidy]

Input  : the newest algo_board_YYYYMMDD.json in "Claude outputs\\boards\\" (a
         board export a chat writes from Notion), or --board PATH.
Output : var\\boards\\ -- clickup_map.json / monday_map.json (card id -> mirror
         id and link) and one report per run. var\\ is gitignored.

Rules for chats: claude/notion_board_protocol_20260919.md in the Project.
Standard library only; tokens come through common.secrets_util.
"""
