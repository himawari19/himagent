def get_tests():
    tests = []
    tc_n  = 1

    tests.append((f"TC-{tc_n:03d} | ", "Positive", "", "", ""))
    tc_n += 1
    tests.append((f"TC-{tc_n:03d} | Project Name - Standard input with alphanumeric chars (edited)", "Positive", "Create Your Project Now! modal is open", "1. Enter Project Name: 'Q1 Marketing Campaign'\n2. Enter Brand Name: 'TestBrand'\n3. Select Category: FMCG & Consumer Goods\n4. Select Project Group: Volare\n5. Select Activity: Prompt Gen\n6. Enter Description: 'test project'\n7. Click [Create Project]", "Project created successfully. All data saved as entered."))
    tc_n += 1
    tests.append((f"TC-{tc_n:03d} | Project Name - With numeric characters", "Positive", "Modal is open", "1. Enter Project Name: 'Project2026V2'\n2. Enter Brand Name: 'TestBrand'\n3. Select Category: E-Commerce & Retail\n4. Select Project Group: Magnus\n5. Select Activity: Image Gen\n6. Click [Create Project]", "Project created. Project Name saved as 'Project2026V2'."))
    tc_n += 1
    tests.append((f"TC-{tc_n:03d} | Project Name - With hyphens and underscores", "Positive", "Modal is open", "1. Enter Project Name: 'Campaign_Launch-Q1'\n2. Enter Brand Name: 'TestBrand'\n3. Select Category: Technology & Startup\n4. Select Project Group: Clabstream\n5. Select Activity: Video Gen\n6. Click [Create Project]", "Project created. Special chars (-, _) accepted."))
    tc_n += 1
    return tests


