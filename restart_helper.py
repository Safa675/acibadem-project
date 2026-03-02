import sys
if "transformers" not in sys.modules:
    try:
        import transformers
        print("Success")
    except Exception as e:
        print("Fail:", e)
