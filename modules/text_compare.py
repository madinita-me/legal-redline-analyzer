import difflib
import re

def split_units(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;:])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]

def compare_texts(old_text: str, new_text: str) -> dict:
    old_units, new_units = split_units(old_text), split_units(new_text)
    matcher = difflib.SequenceMatcher(a=old_units, b=new_units)
    changes, added, removed, index = [], [], [], 1
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal": continue
        old_fragment, new_fragment = "\n".join(old_units[i1:i2]), "\n".join(new_units[j1:j2])
        if tag == "insert": change_type = "добавлено"; added.extend(new_units[j1:j2])
        elif tag == "delete": change_type = "исключено"; removed.extend(old_units[i1:i2])
        else: change_type = "изменено"; added.extend(new_units[j1:j2]); removed.extend(old_units[i1:i2])
        changes.append({"№": index, "Элемент": f"Фрагмент {index}", "Действующая редакция": old_fragment, "Предлагаемая редакция": new_fragment, "Тип изменения": change_type})
        index += 1
    html_diff = difflib.HtmlDiff(wrapcolumn=90).make_table(old_units, new_units, "Действующая", "Предлагаемая")
    return {"changes": changes, "added": added, "removed": removed, "html": html_diff}
