"""@uniccodebot testlari: sqlite (aiosqlite) ustida, Postgres shart emas.

Ishga tushirish: pip install aiosqlite pytest && pytest tests/test_uniccode.py
"""
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import openpyxl
import pytest

pytest.importorskip("aiosqlite")

from uniccode import generator, importer, parsers  # noqa: E402
from uniccode.db import init_db, make_engine, make_sessionmaker  # noqa: E402
from uniccode.excel_out import build_excel  # noqa: E402
from uniccode.generator import Item  # noqa: E402

TZ = ZoneInfo("Asia/Tashkent")
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=TZ)


def run(coro):
    return asyncio.run(coro)


async def _sm(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'uc.db'}")
    await init_db(engine)
    return engine, make_sessionmaker(engine)


def test_format_and_normalize():
    assert generator.normalize_article("x-844088") == "844088"
    assert generator.normalize_article(844088.0) == "844088"
    assert generator.date_part(datetime(2026, 9, 25)) == "2509"
    assert generator.format_code("844088", "CA", "2509", 10002897) == "844088CA250910002897"


def test_generate_sequential_and_new_article(tmp_path):
    async def go():
        engine, sm = await _sm(tmp_path)
        async with sm() as s:
            r1 = await generator.generate(s, [Item("844088", 3), Item("844088", 2, address="TM_6B1")], now=NOW)
        async with sm() as s:
            r2 = await generator.generate(s, [Item("844088", 1)], now=NOW)
        await engine.dispose()
        return r1, r2
    r1, r2 = run(go())
    assert r1.items[0].codes == ["844088CA031010000000", "844088CA031010000001", "844088CA031010000002"]
    assert r1.items[1].codes == ["844088CA031010000003", "844088CA031010000004"]
    assert r2.items[0].codes == ["844088CA031010000005"]


def test_rejects_bad_article(tmp_path):
    async def go():
        engine, sm = await _sm(tmp_path)
        async with sm() as s:
            with pytest.raises(ValueError):
                await generator.generate(s, [Item("84408", 1)], now=NOW)
        await engine.dispose()
    run(go())


def test_concurrent_requests_never_collide(tmp_path):
    async def go():
        engine, sm = await _sm(tmp_path)

        async def one():
            async with sm() as s:
                return await generator.generate(s, [Item("814086", 7), Item("825250", 3)], now=NOW)
        results = await asyncio.gather(*[one() for _ in range(10)])
        await engine.dispose()
        return [c for r in results for ir in r.items for c in ir.codes]
    codes = run(go())
    assert len(codes) == 100 and len(set(codes)) == 100


def _legacy_xlsx(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Датабаза"
    ws.append(["Дата"])
    ws.append(["Дата", "Артикул", "Уникальный код", "Уникальный код"])
    ws.append([datetime(2025, 8, 7, 14, 40), 853205, 10000000, "853205CA082510000000"])
    ws.append([datetime(2025, 8, 7, 14, 40), 853205, 10000001, "853205CA082510000001"])
    ws.append([datetime(2025, 8, 7, 14, 40), 853205, 10000001, "853205CA082510000001"])  # takror
    ws.append([datetime(2026, 1, 3, 9, 55), 899209, 10000004, "899209CA03012610000004"])  # 6 xonali sana
    ws.append([datetime(2026, 9, 18, 22, 19), 844088, 10002896, "844088CA180910002896", "TM_7B1"])
    ws.append([datetime(2025, 8, 9, 12, 15), "x-899071", 10000000, "buzuq"])
    uk = wb.create_sheet("Уник код", 0)  # yasalgan, lekin hali saqlanmagan kod
    uk.append(["CA", "0310", None, 844088, 10002976, "844088CA031010002976", None, 20])
    wb.save(path)


def test_import_then_continue(tmp_path):
    src = tmp_path / "baza.xlsx"
    _legacy_xlsx(src)

    async def go():
        engine, sm = await _sm(tmp_path)
        rows, mx, st = importer.read_legacy(str(src))
        async with sm() as s:
            st = await importer.import_rows(s, rows, mx, st)
        rows2, mx2, st2 = importer.read_legacy(str(src))  # qayta import xavfsiz
        async with sm() as s:
            st2 = await importer.import_rows(s, rows2, mx2, st2)
        async with sm() as s:
            res = await generator.generate(s, [Item("844088", 2), Item("899209", 1), Item("899071", 1)], now=NOW)
        await engine.dispose()
        return st, st2, res
    st, st2, res = run(go())
    assert st.inserted == 5 and st.duplicates_in_file == 1 and st.irregular == 1 and st.invalid == 0
    assert st2.inserted == 0
    assert st.pending_reserved == 1
    assert res.items[0].codes == ["844088CA031010002977", "844088CA031010002978"]
    assert res.items[1].codes == ["899209CA031010000005"]
    assert res.items[2].codes == ["899071CA031010000001"]  # buzuq kod qatoridagi raqam ham hisobga olindi


def _stock_rows():
    hdr = ["Артикул", None, "Номенклатура", None, None, None, "Адрес", "Начальный остаток", "Приход",
           "Расход", "Конечный остаток", "К отбору", "К размещению"]
    def line(art, name, addr, end):
        return [art, None, name, None, None, None, addr, end, None, None, end, None, None]
    return [
        [None] * 13,
        ["Движения товаров на адресных складах"] + [None] * 12,
        ["Параметры:", None, None, "Период: 01/10/2026 - 01/10/2026"] + [None] * 9,
        ["Адрес"] + [None] * 6 + ["Количество упаковок"] + [None] * 5,
        hdr,
        ["TM_9A1"] + [None] * 12,
        line(804066, "X-Co/244/Rich-Ultra/Qaymoq/AL-01/KJ-01/#00", "TM_9A1", 2),
        line(899093, "C-Universal Nakidka Palma/ToqChoko", "TM_9A1", 3),
        line(390181, "FocusEva Cobalt 5D Vanna", "TM_1A1", None),
        line(814220, "C-Co-220/Myunxen/IB8877-01/KJ-01/032", "S_TM-Transit", 5),
        line(450000, "C-Nezamerzayka-20-3L", "S_TM-Transit", 7),
        ["Итого"] + [None] * 12,
    ]


def test_stock_report_selection():
    rep = parsers.parse_stock_report(_stock_rows())
    assert rep and len(rep.lines) == 5 and "01/10/2026" in rep.period
    chosen, skipped = parsers.select_lines(rep, "9,1", only_chexol=False)
    assert [(l.article, l.qty) for l in chosen] == [("804066", 2), ("899093", 3)]
    assert [l.article for l in skipped] == ["390181"]
    chosen, _ = parsers.select_lines(rep, "TM_9A1 S_TM-Transit", only_chexol=True)
    assert [l.article for l in chosen] == ["804066", "814220"]  # nakidka va nezamerzayka chiqmaydi
    assert rep.rows_summary() == {"9": 5, "S_TM-Transit": 12}


def test_list_file_with_series_and_errors():
    rows = [["Артикул", "Кол-во", "Seria", "Наименование"],
            [844088, 3, "T535", "CY-Co-152"],
            ["x-814086", "2", "K1807", None],
            [12345, 1, None, None],
            [844205, 0, None, None],
            ["Итого", 5, None, None]]
    lst = parsers.parse_list(rows)
    assert [(i.article, i.qty, i.series) for i in lst.items] == [("844088", 3, "T535"), ("814086", 2, "K1807")]
    assert lst.items[0].note == "T535"
    assert len(lst.errors) == 2
    headerless = parsers.parse_list([[844088, 2, "P1"], [814086, 1, None]])
    assert [(i.article, i.qty) for i in headerless.items] == [("844088", 2), ("814086", 1)]


def test_excel_output(tmp_path):
    async def go():
        engine, sm = await _sm(tmp_path)
        async with sm() as s:
            r = await generator.generate(s, [Item("844088", 2, address="TM_6B1", series="T1")], now=NOW)
        await engine.dispose()
        return r
    res = run(go())
    p = tmp_path / "o.xlsx"
    p.write_bytes(build_excel(res, title="test"))
    wb = openpyxl.load_workbook(p)
    ws = wb["Kodlar"]
    assert [c.value for c in ws[2]][1:5] == [844088, 10000000, "844088CA031010000000", "TM_6B1"]
    assert wb["Xulosa"].cell(3, 5).value == 2


def test_sheet_sync_uploads_once_and_retries(tmp_path):
    from uniccode.config import UnicSettings
    from uniccode.sheets_sync import SheetSync

    async def go():
        engine, sm = await _sm(tmp_path)
        async with sm() as s:
            await generator.generate(s, [Item("844088", 3, address="TM_6B1")], now=NOW)
        sync = SheetSync(sm, UnicSettings(GSHEET_BATCH=2))
        uploaded, fail = [], {"on": True}

        def fake_append(values):
            if fail["on"]:
                raise ConnectionError("google ishlamayapti")
            uploaded.extend(values)
        sync._append = fake_append
        with pytest.raises(ConnectionError):
            await sync.sync_once()            # xato bo'lsa kodlar kutib turadi
        assert await sync.pending() == 3
        fail["on"] = False
        assert await sync.sync_once() == 2    # GSHEET_BATCH=2
        assert await sync.sync_once() == 1
        assert await sync.sync_once() == 0    # takror yuklanmaydi
        await engine.dispose()
        return uploaded
    up = run(go())
    assert [v[3] for v in up] == ["844088CA031010000000", "844088CA031010000001", "844088CA031010000002"]
    assert up[0][0] == "03/10/2026 12:00:00" and up[0][4] == "TM_6B1"
