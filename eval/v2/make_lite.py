import nbformat
nb=nbformat.read('qabas_eval_v2.ipynb',4)
old_model='''MODEL = "gemini-3.8-flash"                              # model under test (same as earlier runs)

names = [m.name.split("/")[-1] for m in client.models.list() if "gemini" in m.name]
print("Available:", ", ".join(sorted(names)))
assert MODEL in names, f"{MODEL} is not available to this key; pick one from the list above"'''
new_model='''names = [m.name.split("/")[-1] for m in client.models.list() if "gemini" in m.name]
print("Available:", ", ".join(sorted(names)))
# Model under test: the newest stable Flash-Lite this key can use (or type a name from the list above)
MODEL = next((n for n in sorted(names, reverse=True) if "flash-lite" in n and "preview" not in n), None)
assert MODEL, "No Flash-Lite model is available to this key; pick one from the list above and set MODEL by hand"'''
hits=0
for c in nb.cells:
    s=c.source
    if old_model in s: s=s.replace(old_model,new_model); hits+=1
    s=s.replace("qabas_eval_v2_results","qabas_eval_lite_results").replace("qabas_eval_v2","qabas_eval_lite")
    s=s.replace("# Qabas — transcription evaluation v2 (6 published lessons)","# Qabas — transcription evaluation, Flash-Lite run (6 published lessons)")
    s=s.replace("Tests Gemini on 6 lessons","Tests **Gemini Flash-Lite** on 6 lessons (a separate run from the 3.8 Flash notebook, saved in its own folder)")
    c.source=s
assert hits==1
nbformat.write(nb,'/mnt/user-data/outputs/qabas-eval/qabas_eval_lite.ipynb'); print("lite written")
