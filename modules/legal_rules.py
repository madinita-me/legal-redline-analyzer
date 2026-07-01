from __future__ import annotations
from .text_compare import compare_texts
from .templates import DEPARTMENTS

def _contains_any(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return sorted({word for word in words if word.lower() in low})

def _new_terms(old_text: str, new_text: str, words: list[str]) -> list[str]:
    old_low, new_low = old_text.lower(), new_text.lower()
    return sorted({word for word in words if word.lower() in new_low and word.lower() not in old_low})

def _risk_level(flags: dict[str, bool]) -> str:
    score = sum(1 for key in ["new_obligation", "financial", "infrastructure", "authority", "uncertainty", "delegated_order", "liability"] if flags.get(key))
    if score >= 3 or (flags.get("financial") and flags.get("new_obligation")): return "высокий"
    if score >= 1: return "средний"
    return "низкий"

def analyze(old_text: str, new_text: str, metadata: dict, dictionaries: dict[str, list[str]]) -> dict:
    diff = compare_texts(old_text, new_text)
    obligations = _new_terms(old_text, new_text, dictionaries.get("Обязанности", []))
    rights = _new_terms(old_text, new_text, dictionaries.get("Права", []))
    prohibitions = _new_terms(old_text, new_text, dictionaries.get("Запреты", []))
    finance = _new_terms(old_text, new_text, dictionaries.get("Финансовые последствия", []))
    operations = _contains_any(new_text, dictionaries.get("Операционное влияние", []))
    authority = _new_terms(old_text, new_text, dictionaries.get("Полномочия государственных органов", []))
    uncertainty = _contains_any(new_text, dictionaries.get("Риск расширительного толкования", []))
    liability = _new_terms(old_text, new_text, dictionaries.get("Ответственность", []))
    infrastructure = _contains_any(new_text, dictionaries.get("Телеком-инфраструктура", []))
    right_to_obligation = any(w in old_text.lower() for w in ["вправе", "может", "имеет право"]) and any(w in new_text.lower() for w in ["обязан", "должен"])
    delegated_order = any(w in new_text.lower() for w in ["определяет порядок", "утверждает", "в порядке, определяемом"])
    flags = {"new_obligation": bool(obligations) or right_to_obligation, "financial": bool(finance), "infrastructure": bool(infrastructure or operations), "authority": bool(authority), "uncertainty": bool(uncertainty), "delegated_order": delegated_order, "liability": bool(liability)}
    overall = _risk_level(flags)
    substantive = any(flags.values()) or bool(diff["changes"])
    comparison = diff["changes"] or [{"№": 1, "Элемент": "Текст нормы", "Действующая редакция": old_text, "Предлагаемая редакция": new_text, "Тип изменения": "редакционное совпадение" if old_text.strip() == new_text.strip() else "уточнено"}]
    for row in comparison:
        row["Тип изменения"] = classify_change_type(row.get("Тип изменения", ""), row.get("Предлагаемая редакция", ""), flags, right_to_obligation)
    risks = build_risks(flags, obligations, finance, operations, authority, uncertainty, liability, infrastructure)
    summary = (f"Изменение имеет {'содержательный' if substantive else 'преимущественно редакционный'} характер. "
               f"{'Имеются признаки расширения обязанностей Общества. ' if flags['new_obligation'] else 'Прямые признаки расширения обязанностей Общества не выявлены. '}"
               f"Общий уровень риска оценивается как {overall}. "
               f"{'Требуется дополнительное уточнение формулировки и порядка исполнения. ' if flags['uncertainty'] or delegated_order else 'Критичных признаков неопределенности порядка исполнения не выявлено. '}"
               "Изменение может затронуть деятельность Общества при наличии связи с инфраструктурой, финансированием, данными, сетями или взаимодействием с государственными органами.")
    result = {**metadata, "old_text": old_text, "new_text": new_text, "summary": summary, "changes": comparison,
        "added_items": describe_added(diff["added"], obligations, rights, finance, authority, infrastructure, liability),
        "removed_items": describe_removed(diff["removed"], old_text), "semantic_changes": describe_semantics(flags, substantive, new_text),
        "new_obligations": describe_obligations(obligations, flags, infrastructure), "new_rights": describe_rights(rights, authority),
        "prohibitions": describe_prohibitions(prohibitions), "financial": describe_finance(finance), "operations": describe_operations(operations, infrastructure),
        "authority": describe_authority(authority, delegated_order), "uncertainty": describe_uncertainty(uncertainty), "risks": risks, "overall_risk": overall,
        "keywords": {"Обязанности": obligations, "Права": rights, "Запреты": prohibitions, "Финансовые последствия": finance, "Операционное влияние": operations, "Полномочия государственных органов": authority, "Риск расширительного толкования": uncertainty, "Ответственность": liability, "Телеком-инфраструктура": infrastructure}}
    result["final_review"] = build_final_review(result, flags)
    return result

def classify_change_type(base: str, proposed: str, flags: dict[str, bool], right_to_obligation: bool) -> str:
    low = proposed.lower()
    if right_to_obligation: return "право трансформировано в обязанность"
    if any(w in low for w in ["обязан", "должен", "обеспечивает", "предоставляет"]): return "введена новая обязанность"
    if any(w in low for w in ["вправе", "имеет право", "допускается", "разрешается"]): return "введено новое право"
    if any(w in low for w in ["запрещается", "не допускается", "ограничивается"]): return "введено ограничение"
    if flags.get("financial"): return "введен финансовый элемент"
    if flags.get("liability"): return "введена ответственность"
    if flags.get("delegated_order"): return "введена отсылка к подзаконному акту"
    return base if base in ["добавлено", "исключено", "изменено"] else "уточнено"

def describe_added(added, obligations, rights, finance, authority, infrastructure, liability):
    items = list(added[:12])
    for label, values in [("новые обязанности", obligations), ("новые права", rights), ("новые финансовые условия", finance), ("новые полномочия государственных органов", authority), ("новые требования к инфраструктуре, данным, сетям или оборудованию", infrastructure), ("новые основания для ответственности", liability)]:
        if values: items.append(f"Выявлены {label}: {', '.join(values)}.")
    return items or ["Значимые добавления по выбранным критериям не выявлены."]

def describe_removed(removed, old_text):
    items = list(removed[:12]); low = old_text.lower()
    for check in ["права субъектов", "гарантии", "ограничения полномочий госоргана", "условия компенсации", "сроки", "процедурные требования"]:
        if any(word in low for word in check.split()): items.append(f"Необходимо проверить, не исключены ли {check}.")
    return items or ["Значимые исключения по выбранным критериям не выявлены."]

def describe_semantics(flags, substantive, text):
    parts = ["Норма требует смысловой оценки, поскольку изменение не ограничивается только сравнением отдельных слов." if substantive else "Смысловое изменение выражено слабо и может носить редакционный характер."]
    if flags["new_obligation"]: parts.append("Характер нормы может становиться более императивным, а нагрузка на регулируемых субъектов может увеличиваться.")
    if flags["authority"]: parts.append("Степень вмешательства государства может усилиться за счет новых или уточненных полномочий.")
    if flags["uncertainty"]: parts.append("Формулировка допускает более широкое толкование и нуждается в уточнении пределов применения.")
    if "иные" in text.lower(): parts.append("Круг субъектов, объектов или случаев может быть расширен через неопределенные категории.")
    return " ".join(parts)

def describe_obligations(obligations, flags, infrastructure):
    if not flags["new_obligation"]: return "Признаки введения новой обязанности либо расширения действующей обязанности не выявлены."
    text = "В предлагаемой редакции имеются признаки введения новой обязанности либо расширения действующей обязанности. "
    text += f"Ключевые конструкции: {', '.join(obligations) if obligations else 'право может трансформироваться в обязанность'}. "
    text += "Обязанность может потребовать дополнительных организационных, договорных, технических или отчетных действий со стороны Общества. "
    if infrastructure: text += "Связь с инфраструктурой указывает на возможное влияние на сети, оборудование, подключение, передачу данных или взаимодействие с государственным органом."
    return text

def describe_rights(rights, authority):
    if not rights: return "Новые права по ключевым словам не выявлены."
    text = f"Выявлены признаки нового или уточненного права: {', '.join(rights)}. "
    return text + ("Если право предоставлено государственному органу, его реализация может фактически создавать корреспондирующую обязанность для Общества и требовать подзаконного порядка." if authority else "Необходимо проверить, является ли это самостоятельным новым правом или уточнением ранее существующего правомочия.")

def describe_prohibitions(prohibitions):
    if not prohibitions: return "Новые запреты или ограничения по ключевым словам не выявлены."
    return f"Выявлены признаки запрета или ограничения: {', '.join(prohibitions)}. Ограничение может затрагивать услуги, сети, инфраструктуру, договоры или внутренние процессы, включая риск приостановления деятельности, ограничения доступа или запрета отдельных действий."

def describe_finance(finance):
    if not finance: return "Прямые признаки финансовых последствий по ключевым словам не выявлены."
    return "Предлагаемая редакция может повлечь финансовые последствия для Общества, если порядок компенсации, тарифообразования, возмещения затрат или источник финансирования не будут прямо определены. " + f"Выявленные финансовые маркеры: {', '.join(finance)}. Следует проверить риск финансирования мероприятий, наличие источника компенсации, возможность безвозмездного предоставления ресурса, влияние на бюджет, тарифы, договоры и инвестиционные обязательства."

def describe_operations(operations, infrastructure):
    values = sorted(set(operations + infrastructure))
    if not values: return "Прямое операционное влияние на телекоммуникационную или инфраструктурную деятельность по ключевым словам не выявлено."
    return f"Выявлены операционные и инфраструктурные маркеры: {', '.join(values)}. Потенциально могут быть затронуты: {', '.join(DEPARTMENTS)}. Возможное влияние охватывает сети связи, договорные отношения, технические ресурсы, эксплуатационные процессы, внутренние регламенты, взаимодействие с государственными органами и расходы на подключение, сопровождение или обслуживание."

def describe_authority(authority, delegated_order):
    if not authority and not delegated_order: return "Новые признаки усиления полномочий государственных органов по ключевым словам не выявлены."
    found = ", ".join(authority) if authority else "отсылка к порядку, определяемому государственным органом"
    return f"Выявлены признаки полномочий государственных органов: {found}. Необходимо оценить, усиливаются ли полномочия органа, возникает ли зависимость от подзаконного регулирования, определены ли пределы реализации полномочий и сохраняется ли баланс с правами регулируемого субъекта."

def describe_uncertainty(uncertainty):
    if not uncertainty: return "Существенные признаки расширительного толкования по ключевым словам не выявлены."
    return "Формулировка может создавать риск расширительного толкования, поскольку не определены пределы применения нормы, круг субъектов, объем обязанности либо порядок исполнения. " + f"Неопределенные формулировки: {', '.join(uncertainty)}. Такие конструкции могут расширять круг применимых случаев и требуют уточнения пределов применения нормы для снижения правовой неопределенности для Общества."

def build_risks(flags, obligations, finance, operations, authority, uncertainty, liability, infrastructure):
    rows = []
    defs = [("Новая обязанность", flags["new_obligation"], "Появление или расширение обязательного действия для регулируемого субъекта.", "высокий" if flags["financial"] else "средний", "Может потребовать изменения процессов, отчетности, договоров или технических действий.", ", ".join(obligations)), ("Финансовые последствия", flags["financial"], "В норме появились финансовые элементы или расходы.", "высокий", "Возможны дополнительные расходы без ясного механизма компенсации.", ", ".join(finance)), ("Инфраструктурное влияние", flags["infrastructure"], "Норма связана с сетями, оборудованием, подключением, ЦОД или иной инфраструктурой.", "высокий", "Может повлиять на технические ресурсы и эксплуатационные процессы.", ", ".join(sorted(set(operations + infrastructure)))), ("Полномочия государственного органа", flags["authority"], "Расширяются или уточняются полномочия государственного органа.", "средний", "Может повлиять на порядок взаимодействия с регулятором.", ", ".join(authority)), ("Расширительное толкование", flags["uncertainty"], "Использованы неопределенные или открытые формулировки.", "высокий", "Возможна неопределенность объема обязанностей и круга применимых случаев.", ", ".join(uncertainty)), ("Ответственность", flags["liability"], "Появились маркеры ответственности или санкций.", "высокий", "Может увеличить правовые риски при нарушении требований.", ", ".join(liability)), ("Подзаконное регулирование", flags["delegated_order"], "Порядок исполнения может быть передан на уровень подзаконного акта.", "средний", "Возникает зависимость от будущего порядка исполнения.", "Требуется проверка пределов делегирования.")]
    for title, active, desc, level, impact, comment in defs:
        if active: rows.append({"№": len(rows)+1, "Риск": title, "Описание": desc, "Уровень риска": level, "Возможное влияние на Общество": impact, "Комментарий": comment or "Требуется юридическая проверка."})
    return rows or [{"№": 1, "Риск": "Существенные риски не выявлены", "Описание": "По заданным правилам анализа значимые маркеры риска не обнаружены.", "Уровень риска": "низкий", "Возможное влияние на Общество": "Ограниченное.", "Комментарий": "Вывод является предварительным."}]

def build_final_review(result, flags):
    return "\n".join([f"1. Суть изменения. Анализируется изменение нормы по документу: {result.get('document_title') or 'без названия'}, {result.get('article_number') or 'статья/пункт не указаны'}.", f"2. Характер изменения: {'содержательное' if any(flags.values()) else 'преимущественно редакционное'}.", f"3. Потенциальное влияние на права и обязанности Общества. {result['new_obligations']} {result['new_rights']}", f"4. Потенциальное финансовое влияние. {result['financial']}", f"5. Потенциальное операционное влияние. {result['operations']}", f"6. Возможное влияние на взаимодействие с государственными органами. {result['authority']}", f"7. Риски неопределенности и расширительного толкования. {result['uncertainty']}", f"8. Общий уровень риска: {result['overall_risk']}.", "9. Краткий юридический комментарий. Обзор носит предварительный характер и предназначен для выявления юридически значимых изменений, рисков и возможного влияния на деятельность Общества без формирования окончательной позиции Общества."])
