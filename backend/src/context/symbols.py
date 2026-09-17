"""Static symbol bank for dynamic context-word tiles (CONTEXT_PIPELINE_PLAN.md).

Ids are lucide-react export names in kebab-case (e.g. "book-open" -> BookOpen), mirrored 1:1 by
`src/symbols.ts` on the frontend -- see backend/tests/test_symbols.py for the cross-language sync
check. This bank is intentionally separate from the frozen `common/icons.py` IconID enum: that
enum is the 10 fixed AAC board tiles, this bank is symbols the context model may assign to
arbitrary conversation words.
"""

SYMBOL_BANK: tuple[tuple[str, str], ...] = (
    # School
    ("backpack", "bag"),
    ("book-open", "book, reading, page"),
    ("notebook-pen", "notebook, journal, writing"),
    ("pencil", "pencil, draw"),
    ("eraser", "eraser, erase"),
    ("scissors", "scissors, cut"),
    ("ruler", "ruler, measure, length"),
    ("calculator", "calculator, math"),
    ("clipboard-list", "list, checklist, worksheet"),
    ("file-text", "paper, document, essay"),
    ("laptop", "laptop, computer"),
    ("table", "table, desk"),
    ("clock", "clock, time"),
    # Science/tech
    ("flask-conical", "flask, chemistry, experiment"),
    ("beaker", "beaker, liquid"),
    ("test-tube", "test tube, sample"),
    ("microscope", "microscope, cell"),
    ("magnet", "magnet"),
    ("battery", "battery, power"),
    ("cable", "wire, cord"),
    ("plug", "plug, outlet"),
    ("zap", "electricity, spark, energy"),
    ("lightbulb", "bulb, light"),
    ("thermometer", "temperature"),
    ("scale", "scale, weigh, balance"),
    ("rocket", "rocket, launch"),
    ("globe", "world, geography"),
    # Nature/weather
    ("sun", "sun, sunny"),
    ("cloud", "cloud"),
    ("cloud-rain", "rain"),
    ("snowflake", "snow, cold, ice"),
    ("droplets", "water, drops"),
    ("flame", "fire, hot, heat"),
    ("leaf", "leaf"),
    ("flower", "flower"),
    ("tree-pine", "tree"),
    # Animals
    ("cat", "cat"),
    ("dog", "dog"),
    ("bug", "bug, insect"),
    ("rabbit", "rabbit"),
    # Art/music/making
    ("palette", "paint, color"),
    ("paintbrush", "paintbrush, painting"),
    ("shapes", "shapes"),
    ("puzzle", "puzzle, piece"),
    ("blocks", "block, bricks"),
    ("camera", "photo"),
    ("music", "song, music"),
    ("guitar", "guitar"),
    ("mic", "microphone, sing"),
    ("headphones", "listen"),
    ("hammer", "hammer, nail"),
    ("wrench", "wrench, tool, fix"),
    ("box", "box"),
    ("package", "package, delivery"),
    ("recycle", "recycle, trash sorting"),
    ("building", "tower, building"),
    # Food
    ("apple", "apple"),
    ("banana", "banana"),
    ("carrot", "carrot"),
    ("pizza", "pizza"),
    ("sandwich", "sandwich"),
    ("cookie", "cookie"),
    ("cake-slice", "cake"),
    ("cup-soda", "drink, soda"),
    ("glass-water", "glass, water"),
    ("utensils", "lunch, eat, fork"),
    ("ice-cream-cone", "ice cream"),
    # Everyday/people
    ("house", "home, house"),
    ("bus", "bus"),
    ("car", "car"),
    ("shirt", "shirt, clothes"),
    ("bed", "bed, sleep"),
    ("gift", "present"),
    ("coins", "money, coins"),
    ("shopping-cart", "shopping, store"),
    ("phone", "phone"),
    ("users", "group, team, friends"),
    ("hand", "hand, touch"),
    ("heart", "love, like"),
    ("star", "star, favorite"),
    ("trophy", "win, prize"),
    ("party-popper", "party, celebrate"),
    ("gamepad-2", "video game"),
    ("volleyball", "ball, sports"),
    ("bandage", "hurt, band-aid"),
    ("triangle-alert", "danger, careful, warning"),
    # Feelings
    ("smile", "happy"),
    ("frown", "sad"),
    ("angry", "mad"),
    ("laugh", "funny, laughing"),
    ("meh", "bored, so-so"),
)

SYMBOL_IDS: frozenset[str] = frozenset(symbol_id for symbol_id, _ in SYMBOL_BANK)

# Bedrock tool-use can't express an omittable field, so the model always emits a `symbol` string;
# "none" is the explicit sentinel for "no bank entry is a reasonably good literal match", collapsed
# to an absent key at the wiring layer (see common/bedrock.py's _transform_context_tool_output),
# mirroring how flaggedMoment.present is handled.
NO_SYMBOL = "none"

SYMBOL_ENUM: list[str] = sorted(SYMBOL_IDS) + [NO_SYMBOL]


def symbol_bank_prompt_text() -> str:
    """Renders the bank as prompt text: one "- id: hint" line per entry, in bank order."""
    return "\n".join(f"- {symbol_id}: {hint}" for symbol_id, hint in SYMBOL_BANK)
