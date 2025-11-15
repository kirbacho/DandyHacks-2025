document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const fileInput = document.getElementById('fileInput');
    const browseBtn = document.getElementById('browseBtn');
    const uploadArea = document.getElementById('uploadArea');
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const extractBtn = document.getElementById('extractBtn');
    const connectCalendarBtn = document.getElementById('connectCalendarBtn');
    const addToCalendarBtn = document.getElementById('addToCalendarBtn');
    const statusMessage = document.getElementById('statusMessage');
    const calendarPreview = document.getElementById('calendarPreview');
    const noEvents = document.getElementById('noEvents');
    const loadingSpinner = document.getElementById('loadingSpinner');

    let currentFile = null;
    let extractedEvents = [];

    // Check authentication status when page loads
    checkAuthStatus();

    // File upload handling
    browseBtn.addEventListener('click', () => fileInput.click());
    uploadArea.addEventListener('click', () => fileInput.click());

    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.style.borderColor = '#4285f4';
        uploadArea.style.backgroundColor = 'rgba(66, 133, 244, 0.05)';
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.style.borderColor = '#5f6368';
        uploadArea.style.backgroundColor = '';
    });

    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.style.borderColor = '#5f6368';
        uploadArea.style.backgroundColor = '';
        
        if (e.dataTransfer.files.length) {
            handleFileSelection(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFileSelection(e.target.files[0]);
        }
    });

    function handleFileSelection(file) {
        // Validate file type
        const validTypes = ['application/pdf', 'image/jpeg', 'image/jpg', 'image/png'];
        if (!validTypes.includes(file.type)) {
            showStatus('Please upload a PDF, JPG, or PNG file.', 'error');
            return;
        }

        // Validate file size (max 10MB)
        if (file.size > 10 * 1024 * 1024) {
            showStatus('File size must be less than 10MB.', 'error');
            return;
        }

        // Store file and update UI
        currentFile = file;
        fileName.textContent = file.name;
        fileSize.textContent = formatFileSize(file.size);
        fileInfo.style.display = 'flex';
        extractBtn.disabled = false;

        showStatus('File ready for processing. Click "Extract Dates" to continue.', 'info');
    }

    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Extract dates button handler WITH SPINNER
    extractBtn.addEventListener('click', async () => {
        if (!currentFile) return;

        showStatus('Extracting dates from syllabus...', 'info');
        setLoadingState(true, 'extract');

        try {
            const formData = new FormData();
            formData.append('file', currentFile);

            const response = await fetch('http://localhost:5001/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                extractedEvents = result.events;
                displayEvents(extractedEvents);
                addToCalendarBtn.disabled = false;
                showStatus(`✅ Successfully extracted ${extractedEvents.length} events from your syllabus!`, 'success');
            } else {
                throw new Error(result.error || 'Failed to extract dates');
            }
        } catch (error) {
            console.error('Error extracting dates:', error);
            showStatus('❌ Failed to extract dates. Please try again.', 'error');
        } finally {
            setLoadingState(false, 'extract');
        }
    });

    // Connect to Google Calendar button handler
    connectCalendarBtn.addEventListener('click', () => {
        showStatus('Redirecting to Google Calendar authorization...', 'info');
        window.location.href = 'http://localhost:5001/auth/google';
    });

    // Add to Calendar button handler WITH SPINNER
    addToCalendarBtn.addEventListener('click', async () => {
        if (extractedEvents.length === 0) return;

        showStatus('Adding events to your Google Calendar...', 'info');
        setLoadingState(true, 'calendar');

        try {
            const response = await fetch('http://localhost:5001/add-to-calendar', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    events: extractedEvents
                })
            });

            const result = await response.json();

            if (result.success) {
                showStatus(`✅ Successfully added ${result.added_events} events to your Google Calendar!`, 'success');
                addToCalendarBtn.disabled = true;
            } else {
                throw new Error(result.error || 'Failed to add events to calendar');
            }
        } catch (error) {
            console.error('Error adding to calendar:', error);
            showStatus('❌ Failed to add events to calendar. Please try again.', 'error');
        } finally {
            setLoadingState(false, 'calendar');
        }
    });

    // SPINNER FUNCTIONS
    function setLoadingState(loading, type) {
        if (loading) {
            // Show loading spinner
            loadingSpinner.style.display = 'block';
            
            // Update spinner text based on type
            const spinnerText = loadingSpinner.querySelector('p');
            if (type === 'calendar') {
                spinnerText.textContent = 'Adding events to your calendar...';
            } else {
                spinnerText.textContent = 'AI is analyzing your syllabus... This may take 10-20 seconds';
            }
            
            // Disable buttons and add loading states
            document.body.classList.add('loading');
            
            if (type === 'extract') {
                extractBtn.classList.add('btn-loading');
                extractBtn.disabled = true;
                extractBtn.innerHTML = '<span>🔄 Processing...</span>';
            } else if (type === 'calendar') {
                addToCalendarBtn.classList.add('btn-loading');
                addToCalendarBtn.disabled = true;
                addToCalendarBtn.innerHTML = '<span>🔄 Adding to Calendar...</span>';
            }
            
        } else {
            // Hide loading spinner
            loadingSpinner.style.display = 'none';
            
            // Re-enable everything
            document.body.classList.remove('loading');
            
            extractBtn.classList.remove('btn-loading');
            extractBtn.disabled = false;
            extractBtn.innerHTML = '<span>Extract Dates</span>';
            
            addToCalendarBtn.classList.remove('btn-loading');
            addToCalendarBtn.disabled = false;
            addToCalendarBtn.innerHTML = '<span>Add to Google Calendar</span>';
        }
    }

    // Check authentication status
    async function checkAuthStatus() {
        try {
            const response = await fetch('http://localhost:5001/auth-status');
            const result = await response.json();
            
            if (result.authenticated) {
                connectCalendarBtn.innerHTML = '<span>✅ Connected to Google Calendar</span>';
                connectCalendarBtn.disabled = true;
                showStatus('Already connected to Google Calendar!', 'success');
                setTimeout(() => {
                    statusMessage.style.display = 'none';
                }, 3000);
            }
        } catch (error) {
            console.log('Not authenticated with Google Calendar');
        }
    }

    function displayEvents(events) {
        calendarPreview.innerHTML = '';

        if (events.length === 0) {
            calendarPreview.appendChild(noEvents);
            noEvents.style.display = 'block';
            return;
        }

        noEvents.style.display = 'none';

        events.forEach(event => {
            const eventElement = document.createElement('div');
            eventElement.className = 'event-item';
            
            const title = document.createElement('div');
            title.className = 'event-title';
            title.textContent = event.title;
            
            const details = document.createElement('div');
            details.className = 'event-details';
            
            const dateSpan = document.createElement('span');
            dateSpan.textContent = formatEventDate(event);
            
            const timeSpan = document.createElement('span');
            timeSpan.textContent = formatEventTime(event);
            
            details.appendChild(dateSpan);
            details.appendChild(timeSpan);
            
            eventElement.appendChild(title);
            eventElement.appendChild(details);
            
            calendarPreview.appendChild(eventElement);
        });
    }

    function formatEventDate(event) {
        if (event.recurring) {
            return `Every ${event.recurrence_pattern}`;
        }
        return event.date;
    }

    function formatEventTime(event) {
        if (event.start_time && event.end_time) {
            return `${event.start_time} - ${event.end_time}`;
        } else if (event.start_time) {
            return `${event.start_time}`;
        }
        return 'All day';
    }

    function showStatus(message, type) {
        statusMessage.textContent = message;
        statusMessage.className = 'status-message';
        
        switch(type) {
            case 'success':
                statusMessage.classList.add('status-success');
                break;
            case 'error':
                statusMessage.classList.add('status-error');
                break;
            case 'info':
                statusMessage.classList.add('status-info');
                break;
        }
        
        statusMessage.style.display = 'block';
        
        // Auto-hide success messages after 5 seconds
        if (type === 'success') {
            setTimeout(() => {
                statusMessage.style.display = 'none';
            }, 5000);
        }
    }

    // Check URL parameters for auth success/error
    function checkUrlParams() {
        const urlParams = new URLSearchParams(window.location.search);
        const authStatus = urlParams.get('auth');
        
        if (authStatus === 'success') {
            showStatus('Successfully connected to Google Calendar!', 'success');
            connectCalendarBtn.innerHTML = '<span>✅ Connected to Google Calendar</span>';
            connectCalendarBtn.disabled = true;
            
            // Clean URL
            window.history.replaceState({}, document.title, window.location.pathname);
        } else if (authStatus === 'error') {
            showStatus('Failed to connect to Google Calendar. Please try again.', 'error');
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    }

    // Check URL parameters when page loads
    checkUrlParams();
});