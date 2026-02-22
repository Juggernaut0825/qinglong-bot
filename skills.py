# ── Tool definitions for the LLM ──────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "Get current weather or forecast for a location. Always require a location from the user first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name or airport code"},
                    "mode": {
                        "type": "string",
                        "enum": ["current", "forecast", "week"],
                        "description": "current = now, forecast = 3-day, week = 7-day",
                    },
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize",
            "description": "Summarize a URL, article, YouTube video, or file path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "URL or file path to summarize"},
                    "length": {
                        "type": "string",
                        "enum": ["short", "medium", "long"],
                        "description": "Desired summary length",
                    },
                },
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lark_doc",
            "description": "Lark document operations: read, write, append, create, list_blocks, get_block, update_block, delete_block.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["read", "write", "append", "create", "list_blocks", "get_block", "update_block", "delete_block"],
                    },
                    "doc_token": {"type": "string", "description": "Document token from URL"},
                    "content": {"type": "string", "description": "Markdown content for write/append/update_block"},
                    "title": {"type": "string", "description": "Title for create action"},
                    "folder_token": {"type": "string", "description": "Folder token for create action"},
                    "block_id": {"type": "string", "description": "Block ID for block operations"},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lark_perm",
            "description": "Manage Lark document permissions: list, add, or remove collaborators.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "add", "remove"]},
                    "token": {"type": "string", "description": "Document/folder token"},
                    "type": {"type": "string", "enum": ["doc", "docx", "sheet", "bitable", "folder", "file", "wiki", "mindnote"]},
                    "member_type": {"type": "string", "enum": ["email", "openid", "userid", "unionid", "openchat", "opendepartmentid"]},
                    "member_id": {"type": "string"},
                    "perm": {"type": "string", "enum": ["view", "edit", "full_access"]},
                },
                "required": ["action", "token", "type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "llava",
            "description": "Analyze an image: describe, answer questions, read text in images. Use when user sends an image.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_url": {"type": "string", "description": "URL of the image to analyze"},
                    "question": {"type": "string", "description": "Question about the image"},
                },
                "required": ["image_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nano_pdf",
            "description": "Edit a PDF page with natural-language instructions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the PDF file"},
                    "page": {"type": "integer", "description": "Page number (1-based)"},
                    "instruction": {"type": "string", "description": "Natural-language edit instruction"},
                },
                "required": ["file_path", "page", "instruction"],
            },
        },
    },
]
