def test_core_imports():
    from app.main import app

    assert app.title == "Workforce Attendance & Payroll API"
    assert app.version == "0.3.0"
