import requests
import json

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0ZGI3MDM4Zi1mYTg5LTQxYmMtOTI1Yy0zODM4NDIyOWM3OTUiLCJlbWFpbCI6Im1hbmFnZXIubXpoQGVma28ubG9jYWwiLCJyb2xlIjoibWFuYWdlciIsImZ1bGxOYW1lIjoi0KLQuNC80L7RhNC10LXQsiDQktC40YLQsNC70LjQuSDQmNC70YzQuNGHIiwiZW1wbG95ZWVJZCI6IjZjODRmZGZhLWQyNDktNGM2Mi05NmI5LTExMzQwYjdmMWJkNCIsImlhdCI6MTc3ODA4OTYxMiwiZXhwIjoxNzc4Njk0NDEyLCJpc3MiOiJFRktPLUFPIn0.nugArK4AtmpUahx1rufmRs3Tdz6o9e7eCwxzQKi0p7U"

all_positions = []
page = 0
page_size = 500

while True:
    url = f"https://microkernel-kmpo.duckdns.org/api/personnel/positions?skip={page * page_size}&take={page_size}"
    print(f"Загружаем страницу {page + 1}...")
    r = requests.get(url, headers={"Authorization": f"Bearer {TOKEN}"})
    
    if r.status_code != 200:
        # Пробуем другие названия параметров
        url2 = f"https://microkernel-kmpo.duckdns.org/api/personnel/positions?offset={page * page_size}&limit={page_size}"
        r = requests.get(url2, headers={"Authorization": f"Bearer {TOKEN}"})
        
    if r.status_code != 200:
        print(f"Ошибка: {r.status_code}")
        break
        
    data = r.json()
    
    if isinstance(data, dict):
        batch = data.get("positions") or data.get("data") or []
    else:
        batch = data
        
    if not batch:
        break
        
    all_positions.extend(batch)
    print(f"   Загружено {len(batch)} должностей, всего {len(all_positions)}")
    
    if len(batch) < page_size:
        break
    page += 1

print(f"\n✅ Всего должностей в ядре: {len(all_positions)}")

# Сохраняем в файл
with open("positions.json", "w", encoding="utf-8") as f:
    json.dump(all_positions, f, ensure_ascii=False, indent=2)

print("✅ Сохранено в positions.json")