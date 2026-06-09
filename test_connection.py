from db.supabase_client import supabase

try:
    result = supabase.table("tenders").select("*").limit(1).execute()
    print("✅ Supabase connection successful")
    print(f"   Tenders table exists, rows: {len(result.data)}")
except Exception as e:
    print(f"❌ Connection failed: {e}")
