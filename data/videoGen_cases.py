def get_test_cases():
    test_cases = []
    
    def add(scenario, test_name, case_type, precond, steps, expected):
        test_cases.append((scenario, test_name, case_type, precond, steps, expected))
        
    add('NAVBAR.LOGO', 'Verify logo link navigates to home', 'Positive', 'AI Video Generator page is open', '1. Click on the Navbar Logo.', 'The page redirects back to the homepage.')
    add('FRAME.UPLOAD_START', 'Upload valid PNG for Start Frame', 'Positive', 'Start Frame upload box is visible', '1. Click on Start Frame upload box.\n2. Choose a valid 2MB PNG file.', 'The upload succeeds and thumbnail of PNG is displayed in the box.')
    add('ADVANCED.DURATION', 'Select duration 6s', 'Positive', 'Duration options are visible', '1. Click on the "6s" duration button.', 'The button is selected and duration state is set to 6 seconds.')
    return test_cases
