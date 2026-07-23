import os
import hashlib
import json
import re
from datetime import datetime

# 設定路徑
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
RECIPES_DIR = os.path.join(WORKSPACE_DIR, "Recipes")
DATABASE_FILE = os.path.join(WORKSPACE_DIR, "database.json")

def calculate_md5(file_path):
    """計算檔案的 MD5 Hash"""
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()
    except Exception as e:
        print(f"無法計算檔案 MD5 {file_path}: {e}")
        return None

def parse_markdown(file_path):
    """解析 Markdown 檔案中的 Frontmatter 與主要內容"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"無法讀取檔案 {file_path}: {e}")
        return None

    # 初始化元資料
    meta = {
        "title": os.path.basename(file_path).replace(".md", ""),
        "tags": [],
        "author": "未知",
        "source": "",
        "summary": "",
        "content": ""
    }

    # 正則表達式比對 Frontmatter
    frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    
    body_content = content
    if frontmatter_match:
        yaml_content = frontmatter_match.group(1)
        body_content = content[frontmatter_match.end():]
        
        # 解析簡單的 YAML 鍵值對
        for line in yaml_content.split('\n'):
            line = line.strip()
            if not line or ':' not in line:
                continue
            
            key, val = line.split(':', 1)
            key = key.strip()
            val = val.strip()
            
            # 清除引號
            val = re.sub(r'^["\']|["\']$', '', val)
            
            if key == "title":
                meta["title"] = val
            elif key == "author":
                meta["author"] = val
            elif key == "source":
                meta["source"] = val
            elif key == "tags":
                # 處理兩種常見的 Tags 格式:
                # 1. tags: ["tag1", "tag2"]
                # 2. tags:
                #      - tag1
                #      - tag2
                if val.startswith('[') and val.endswith(']'):
                    tags_list = [t.strip().strip('"\'') for t in val[1:-1].split(',')]
                    meta["tags"] = [t for t in tags_list if t]
                else:
                    # 可能是後續行條目，待會兒以多行處理，此處先記錄
                    pass
        
        # 針對縮排式 tags 的多行處理
        if not meta["tags"] and "tags:" in yaml_content:
            tags_section = False
            for line in yaml_content.split('\n'):
                if line.strip().startswith('tags:'):
                    tags_section = True
                    continue
                if tags_section:
                    # 遇到下一個沒有縮排的鍵則結束
                    if line and not line.startswith(' ') and not line.startswith('\t'):
                        tags_section = False
                        continue
                    match = re.match(r'^\s*-\s*(.+)$', line)
                    if match:
                        meta["tags"].append(match.group(1).strip().strip('"\''))

    # 清除 body_content 中的 Markdown 語法以做成摘要
    clean_text = re.sub(r'[#*`_\-\[\]()#]', '', body_content)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    meta["summary"] = clean_text[:150] + ("..." if len(clean_text) > 150 else "")
    meta["content"] = body_content.strip()
    
    return meta

def main():
    print("====== 開始更新食譜知識庫索引 ======")
    
    if not os.path.exists(RECIPES_DIR):
        print(f"錯誤：找不到食譜資料夾 '{RECIPES_DIR}'。請確認目前目錄結構。")
        return

    # 讀取舊的資料庫
    db = {"last_updated": "", "recipes": {}}
    if os.path.exists(DATABASE_FILE):
        try:
            with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
                db = json.load(f)
        except Exception as e:
            print(f"警告：讀取 database.json 失敗，將重新建立庫。錯誤: {e}")

    existing_recipes = db.get("recipes", {})
    new_recipes = {}
    
    updated_count = 0
    created_count = 0
    unchanged_count = 0
    
    # 遍歷 Recipes 目錄
    for root, _, files in os.walk(RECIPES_DIR):
        for file in files:
            if not file.endswith(".md"):
                continue
                
            abs_path = os.path.join(root, file)
            rel_path = os.path.relpath(abs_path, WORKSPACE_DIR).replace('\\', '/')
            
            current_hash = calculate_md5(abs_path)
            if not current_hash:
                continue
                
            # 判斷是否需要更新
            is_new = rel_path not in existing_recipes
            is_changed = not is_new and existing_recipes[rel_path].get("md5") != current_hash
            
            if is_new or is_changed:
                meta = parse_markdown(abs_path)
                if meta:
                    meta["md5"] = current_hash
                    new_recipes[rel_path] = meta
                    if is_new:
                        print(f"[新增] {rel_path}")
                        created_count += 1
                    else:
                        print(f"[修改] {rel_path}")
                        updated_count += 1
            else:
                # 保持原樣
                new_recipes[rel_path] = existing_recipes[rel_path]
                unchanged_count += 1

    # 找出被刪除的檔案
    deleted_count = 0
    for rel_path in list(existing_recipes.keys()):
        if rel_path not in new_recipes:
            print(f"[刪除] {rel_path}")
            deleted_count += 1

    # 判斷是否有變動，決定是否寫入檔案
    js_file = DATABASE_FILE.replace(".json", ".js")
    has_changes = created_count > 0 or updated_count > 0 or deleted_count > 0 or not os.path.exists(js_file)
    
    if has_changes:
        db["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db["recipes"] = new_recipes
        
        try:
            with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
                json.dump(db, f, ensure_ascii=False, indent=2)
            
            # 同時寫入 database.js 以免除本地開發跨域限制 (CORS)
            with open(js_file, 'w', encoding='utf-8') as f:
                f.write(f"window.RECIPE_DB = {json.dumps(db, ensure_ascii=False, indent=2)};")
                
            print(f"\n成功更新索引庫！")
            print(f"新增: {created_count} 筆，修改: {updated_count} 筆，刪除: {deleted_count} 筆，未異動: {unchanged_count} 筆。")
            print(f"資料庫存於: {DATABASE_FILE}")
        except Exception as e:
            print(f"寫入 database.json 失敗: {e}")
    else:
        print(f"\n無任何食譜檔案異動，略過索引庫更新。")
        print(f"未異動: {unchanged_count} 筆。")
        
    print("====== 更新完畢 ======")

if __name__ == "__main__":
    main()
