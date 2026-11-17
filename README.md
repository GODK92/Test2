# 🛒 쇼핑 리스트

아이템 추가, 수정, 삭제, 체크가 가능한 간단한 Streamlit 웹 앱입니다. 자세한 요구사항은 `PRD.md`를 참고하세요.

## 로컬 실행

Python 3.10 이상이 필요합니다.

```bash
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 http://localhost:8501 로 접속합니다.

## 데이터 저장

- 처음 접속하면 주소에 `?u=<12자리 ID>`가 붙고, 이 ID별로 `data/<ID>.json`에 리스트를 저장합니다.
- 새로고침해도 같은 리스트가 유지됩니다. **이 주소를 북마크해 두면 나중에도 같은 리스트를 열 수 있습니다.** 주소에서 `?u=...`를 빼고 접속하면 새 리스트가 시작됩니다.
- 같은 주소를 여러 탭/기기에서 열어도 변경 내용이 서로 합쳐집니다.
- 제한: 물건 이름 최대 100자, 리스트당 최대 200개.
- `data/` 폴더는 `.gitignore`에 포함되어 저장소에 올라가지 않습니다.

## 배포 (Streamlit Community Cloud)

1. 이 폴더를 GitHub 저장소에 올립니다 (`app.py`, `requirements.txt`, `.streamlit/config.toml` 포함).
2. https://share.streamlit.io 에서 저장소, 브랜치, `app.py`를 지정해 Deploy 합니다.

**주의:** Community Cloud는 앱이 재시작되거나 슬립에서 깨어날 때 `data/` 폴더가 초기화될 수 있습니다. 배포 후에도 데이터를 계속 보관해야 하면 Google Sheets, Supabase 같은 외부 저장소로 바꿔야 합니다.
