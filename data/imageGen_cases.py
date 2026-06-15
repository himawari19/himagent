def get_test_cases():
    test_cases = []
    
    def add(scenario, test_name, case_type, precond, steps, expected):
        test_cases.append((scenario, test_name, case_type, precond, steps, expected))
        
    add('NAVBAR.LOGO', 'Verify logo link navigates to home', 'Positive', 'AI Image Generator page is open', '1. Click on the Navbar Logo element.', 'The page redirects back to the main homepage successfully.')
    add('MODEL.DROPDOWN', 'Select Nano Banana Pro', 'Positive', 'Model dropdown is expanded', '1. Click Model dropdown.\n2. Select "Nano Banana Pro" model from list.', 'Selected model name is displayed on the dropdown button.')
    add('ADVANCED.RATIO', 'Select aspect ratio 16:9', 'Positive', 'Aspect Ratio options are visible', '1. Click on the "16:9" ratio button.', 'The button is highlighted and selected aspect ratio state is updated.')
    return test_cases
