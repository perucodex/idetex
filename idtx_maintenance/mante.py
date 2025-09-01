import requests
from openpyxl import Workbook

URL = "https://one.fracttal.com/rpc/proxy"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "content-type": "application/json",
    "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IlVPWmpZQ0tmS1RobEhKM0FlYmZPdUlkZWZ2TUUzNENYa1R1SUVuSEJyakhmIiwiaWRfY29tcGFueSI6ODMwLCJlbWFpbCI6Imd1aWxsZXJtb0BmdWxscGltYS5jb20ucGUiLCJpZF9zZXJ2ZXIiOiJBTUVSSUNBTiIsImlhdCI6MTc1NjQwMDk1OSwiZXhwIjoxNzU2NDQ0MTU5fQ.96FB4q5R2cncyrc_yk0caOXtBmB-aLY1gErR2N6sDqY",  # ⚠️ no lo cambies
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
    "x-version": "Fracttal/5.1.10 web",
    "origin": "https://one.fracttal.com",
    "referer": "https://one.fracttal.com/tasks/task",
}

# ==========================
# API Calls
# ==========================
def get_task_groups(page=1, limit=100):
    payload = [{
        "id": "req-groups",
        "jsonrpc": "2.0",
        "method": "tasks.groups_tasks_list",
        "params": {"filter": [], "sort": [], "page": page, "limit": limit, "start": (page-1)*limit}
    }]
    resp = requests.post(URL, headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()[0]["result"]["data"]

def get_group_assets(group_id, page=1, limit=100):
    payload = [{
        "id": f"req-assets-{group_id}",
        "jsonrpc": "2.0",
        "method": "tasks.groups_tasks_list_assets",
        "params": {
            "filter": [],
            "sort": [],
            "page": page,
            "limit": limit,
            "start": (page-1)*limit,
            "is_tree": False,
            "node": None,
            "id_group_task": group_id
        }
    }]
    resp = requests.post(URL, headers=HEADERS, json=payload)
    resp.raise_for_status()
    result = resp.json()[0].get("result", {})
    return result.get("data") or []

def get_tasks(group_id, page=1, limit=100):
    payload = [{
        "id": f"req-tasks-{group_id}",
        "jsonrpc": "2.0",
        "method": "tasks.tasks_list",
        "params": {
            "filter": [{"property": "id_group_task", "value": group_id}],
            "sort": [],
            "page": page,
            "limit": limit,
            "start": (page-1)*limit,
            "is_tree": False,
            "node": 0
        }
    }]
    resp = requests.post(URL, headers=HEADERS, json=payload)
    resp.raise_for_status()
    result = resp.json()[0].get("result", {})
    return result.get("data") or []

def _extract_list_from_result(result: dict):
    if not isinstance(result, dict):
        return []
    for key in ("items", "data", "rows", "list"):
        val = result.get(key)
        if isinstance(val, list):
            return val
    for v in result.values():
        if isinstance(v, list):
            return v
    return []

def get_subtasks(task_id, page=1, limit=200):
    payload = [{
        "id": f"req-subtasks-{task_id}",
        "jsonrpc": "2.0",
        "method": "tasks.tasks_form_items_list",
        "params": {
            "filter": [],
            "sort": [],
            "page": page,
            "limit": limit,
            "start": (page-1)*limit,
            "is_tree": False,
            "node": None,
            "id_task": task_id
        }
    }]
    resp = requests.post(URL, headers=HEADERS, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return _extract_list_from_result(data[0].get("result", {}))

def get_task_triggers(task_id, page=1, limit=100):
    payload = [{
        "id": f"req-triggers-{task_id}",
        "jsonrpc": "2.0",
        "method": "tasks.tasks_triggers_list",
        "params": {
            "page": page,
            "limit": limit,
            "start": (page - 1) * limit,
            "is_tree": False,
            "node": None,
            "id_task": task_id
        }
    }]
    resp = requests.post(URL, headers=HEADERS, json=payload)
    resp.raise_for_status()
    result = resp.json()[0].get("result", {})
    return result.get("data") or []

# ==========================
# Exportar a Excel
# ==========================
def export_to_excel(groups_with_data, filename="fracttal_data.xlsx"):
    wb = Workbook()
    ws = wb.active
    ws.title = "Fracttal Data"

    # Encabezados (agregamos Duration + Trigger fields)
    ws.append(["Grupo", "equipment_id", "name", "maintenance_type", "duration", "instruction_text", "repeat_unit", "repeat_interval","repeat_type","recurring_maintenance"])

    for g in groups_with_data:
        group_name = g.get("description", f"Grupo {g['id']}")
        assets = g.get("assets", [])
        tasks = g.get("tasks", [])

        if not assets and not tasks:
            ws.append([group_name, "", "", "", "", "", "", ""])
            continue

        if not assets and tasks:
            assets = [{"field_1": ""}]

        last_group = None
        for asset in assets:
            field_1 = asset.get("field_1", "")

            if not tasks:
                row_group = group_name if last_group != group_name else ""
                ws.append([row_group, field_1, "", "", "", "", "", ""])
                last_group = group_name
                continue

            last_asset = None
            for t in tasks:
                task_name = t.get("description", f"Tarea {t['id']}")
                task_type = 'preventive' if t.get("tasks_types_main_description", f"Tarea {t['id']}") == 'PREVENTIVO' and t.get("tasks_types_main_description", f"Tarea {t['id']}") else 'corrective'
                duration = t.get("duration", "")/60/60
                subtasks = t.get("subtasks", [])
                triggers = t.get("triggers", [])

                if not subtasks and not triggers:
                    row_group = group_name if last_group != group_name else ""
                    row_asset = field_1 if last_asset != field_1 else ""
                    ws.append([row_group, row_asset, task_name, task_type, duration, "", "", ""])
                    last_group = group_name
                    last_asset = field_1
                    continue

                # Subtareas + triggers
                max_len = max(len(subtasks), len(triggers))
                sub_name = ''
                for i in range(max_len):
                    x_sub_name = subtasks[i]["description"] if i < len(subtasks) else ""
                    sub_group_desc = subtasks[i].get("task_form_item_group_description", "") if i < len(subtasks) else ""
                    sub_name += f'<h3 data-oe-version="1.2">Tarea {i+1}</h3><div>{x_sub_name}</div><div>Grupo / Parte: {sub_group_desc}</div>'
                    if i == 0:
                        trig_period = triggers[i]["period_date_description"] if i < len(triggers) else ""
                        trig_value = triggers[i]["value_main"] if i < len(triggers) else "1"

                        trig_period = 'day' if trig_period == 'DAYS' else trig_period
                        trig_period = 'week' if trig_period == 'WEEKS' else trig_period
                        trig_period = 'month' if trig_period == 'MONTHS' else trig_period
                        trig_period = 'year' if trig_period == 'YEARS' else trig_period

                    row_group = group_name if last_group != group_name else ""
                    row_asset = field_1
                    # if i == 0:
                    #     ws.append([row_group, row_asset, task_name, task_type, duration, sub_name, trig_period, trig_value])
                    #     last_group = group_name
                    #     last_asset = field_1
                    # else:
                    #     ws.append(["", field_1, "", "", "", sub_name, trig_period, trig_value])
                ws.append([row_group, row_asset, task_name, task_type, duration, sub_name, trig_period, trig_value,'forever','TRUE'])

    wb.save(filename)
    print(f"✅ Exportado a {filename}")

# ==========================
# Main
# ==========================
if __name__ == "__main__":
    groups = get_task_groups(page=1, limit=100)
    groups_with_data = []

    for g in groups:
        # assets con field_1
        assets = get_group_assets(g["id"])
        g["assets"] = assets

        # tareas + subtareas
        tasks = get_tasks(g["id"])
        for t in tasks:
            subtasks = get_subtasks(t["id"])
            triggers = get_task_triggers(t["id"])
            t["subtasks"] = subtasks
            t["triggers"] = triggers
        g["tasks"] = tasks

        groups_with_data.append(g)

    export_to_excel(groups_with_data)
