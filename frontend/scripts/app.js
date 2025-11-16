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
    const loadingSpinner = document.getElementById('loadingSpinner');
    const noEvents = document.getElementById('noEvents');

    let currentFile = null;
    let extractedEvents = [];
    let studyEvents = [];

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

    // Extract dates button handler
    extractBtn.addEventListener('click', async () => {
        if (!currentFile) return;

        showStatus('Extracting dates and planning study sessions...', 'info');
        setLoadingState(true);

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
                
                // Generate smart study sessions with AI resources
                studyEvents = await generateSmartStudySessions(extractedEvents);
                
                // Display all events
                displayEvents([...extractedEvents, ...studyEvents]);
                addToCalendarBtn.disabled = false;
                
                showStatus(`✅ Extracted ${extractedEvents.length} events and added ${studyEvents.length} smart study sessions!`, 'success');
            } else {
                throw new Error(result.error || 'Failed to extract dates');
            }
        } catch (error) {
            console.error('Error extracting dates:', error);
            showStatus('Failed to extract dates. Please try again.', 'error');
        } finally {
            setLoadingState(false);
        }
    });

    // Smart study session generation with AI resources
    async function generateSmartStudySessions(events) {
        const studySessions = [];
        
        // Get existing calendar events to avoid conflicts
        const existingEvents = await getExistingCalendarEvents();
        
        // Process each event that needs study sessions
        for (const event of events) {
            const title = event.title.toLowerCase();
            
            if (title.includes('exam') || title.includes('midterm') || title.includes('final') || title.includes('test')) {
                // Get AI-generated study sessions with resources
                const sessionsWithResources = await createStudySessionsWithResources(event, existingEvents, [7, 3, 1]);
                studySessions.push(...sessionsWithResources);
            }
            
            if (title.includes('project') || title.includes('paper') || title.includes('assignment')) {
                const workSessions = createConflictFreeWorkBlocks(event, existingEvents, [5, 2]);
                studySessions.push(...workSessions);
            }
        }
        
        return studySessions;
    }

    async function createStudySessionsWithResources(examEvent, existingEvents, daysBefore) {
        // Call backend to get sessions with AI-generated resources
        try {
            const response = await fetch('http://localhost:5001/generate-study-sessions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    exam_event: examEvent,
                    days_before: daysBefore
                })
            });
            
            const result = await response.json();
            if (result.success) {
                return result.study_sessions;
            }
        } catch (error) {
            console.log('Failed to get AI study sessions, using basic ones');
        }
        
        // Fallback to basic study sessions
        return createConflictFreeStudyBlocks(examEvent, existingEvents, daysBefore);
    }

    function createConflictFreeStudyBlocks(examEvent, existingEvents, daysBefore) {
        const blocks = [];
        const examDate = new Date(examEvent.date);
        
        daysBefore.forEach(days => {
            const studyDate = new Date(examDate);
            studyDate.setDate(studyDate.getDate() - days);
            
            // Find a time that doesn't conflict with existing events
            const optimalTime = findOptimalTime(studyDate, existingEvents, 'evening');
            
            // Different focus for each study session
            const sessionFocus = getSessionFocus(days, daysBefore.length);
            
            blocks.push({
                title: `📚 ${sessionFocus} for ${examEvent.title}`,
                date: studyDate.toISOString().split('T')[0],
                start_time: optimalTime.start,
                end_time: optimalTime.end,
                recurring: false,
                description: `${sessionFocus} session for ${examEvent.title}`,
                type: 'study-session',
                source: 'auto_generated',
                study_resources: [
                    "Review lecture notes and slides",
                    "Practice problems from textbook",
                    "Watch relevant tutorial videos",
                    "Form study group with classmates"
                ]
            });
        });
        
        return blocks;
    }

    function createConflictFreeWorkBlocks(assignmentEvent, existingEvents, daysBefore) {
        const blocks = [];
        const dueDate = new Date(assignmentEvent.date);
        
        daysBefore.forEach(days => {
            const workDate = new Date(dueDate);
            workDate.setDate(workDate.getDate() - days);
            
            // Find optimal time avoiding conflicts
            const optimalTime = findOptimalTime(workDate, existingEvents, 'evening');
            
            blocks.push({
                title: `💻 Work on ${assignmentEvent.title}`,
                date: workDate.toISOString().split('T')[0],
                start_time: optimalTime.start,
                end_time: optimalTime.end,
                recurring: false,
                description: `Focused work session for ${assignmentEvent.title}`,
                type: 'study-session', 
                source: 'auto_generated'
            });
        });
        
        return blocks;
    }

    function getSessionFocus(daysUntilExam, totalSessions) {
        if (totalSessions === 3) {
            if (daysUntilExam === 7) return "Comprehensive Review";
            if (daysUntilExam === 3) return "Practice Problems";
            return "Final Review";
        } else if (totalSessions === 2) {
            if (daysUntilExam === 5) return "Concept Review";
            return "Practice Session";
        }
        return "Study Session";
    }

    function findOptimalTime(date, existingEvents, preference) {
        // Default to evening study sessions (7-9 PM)
        let optimal = { start: '19:00', end: '21:00' };
        
        // Check if this conflicts with existing events
        const dateStr = date.toISOString().split('T')[0];
        const conflictingEvent = existingEvents.find(event => 
            event.date === dateStr && 
            event.start_time === optimal.start
        );
        
        // If conflict, try alternative times
        if (conflictingEvent) {
            if (preference === 'evening') {
                optimal = { start: '20:00', end: '22:00' }; // Try later
            } else {
                optimal = { start: '18:00', end: '20:00' }; // Try earlier
            }
        }
        
        return optimal;
    }

    async function getExistingCalendarEvents() {
        try {
            const response = await fetch('http://localhost:5001/calendar-events');
            const result = await response.json();
            return result.events || [];
        } catch (error) {
            console.log('Could not fetch existing events, using default times');
            return [];
        }
    }

    // Display events with study resources
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
            eventElement.className = `event-item ${event.type || ''}`;
            
            const title = document.createElement('div');
            title.className = 'event-title';
            title.textContent = event.title;
            
            // Add type badge for study sessions
            if (event.type === 'study-session') {
                const badge = document.createElement('span');
                badge.className = 'event-type-badge study';
                badge.textContent = 'STUDY';
                title.appendChild(badge);
            }
            
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
            
            // ADD STUDY RESOURCES FOR STUDY SESSIONS
            if (event.type === 'study-session' && event.study_resources) {
                const resourcesContainer = document.createElement('div');
                resourcesContainer.className = 'study-resources';
                
                const resourcesTitle = document.createElement('div');
                resourcesTitle.className = 'resources-title';
                resourcesTitle.textContent = '📚 Study Resources:';
                resourcesContainer.appendChild(resourcesTitle);
                
                const resourcesList = document.createElement('ul');
                resourcesList.className = 'resources-list';
                
                event.study_resources.forEach(resource => {
                    const resourceItem = document.createElement('li');
                    resourceItem.textContent = resource;
                    resourcesList.appendChild(resourceItem);
                });
                
                resourcesContainer.appendChild(resourcesList);
                eventElement.appendChild(resourcesContainer);
            }
            
            calendarPreview.appendChild(eventElement);
        });
    }

    // Google Calendar integration
    connectCalendarBtn.addEventListener('click', () => {
        showStatus('Redirecting to Google Calendar authorization...', 'info');
        window.location.href = 'http://localhost:5001/auth/google';
    });

    addToCalendarBtn.addEventListener('click', async () => {
        if (extractedEvents.length === 0) return;

        showStatus('Adding events to your Google Calendar...', 'info');
        setLoadingState(true);

        try {
            const allEvents = [...extractedEvents, ...studyEvents];
            
            const response = await fetch('http://localhost:5001/add-to-calendar', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    events: allEvents
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
            showStatus('Failed to add events to calendar. Please try again.', 'error');
        } finally {
            setLoadingState(false);
        }
    });

    // Utility functions
    function formatEventDate(event) {
        if (event.recurring) {
            return `Every ${event.recurrence_pattern}`;
        }
        const date = new Date(event.date);
        return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
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
        
        if (type === 'success') {
            setTimeout(() => {
                statusMessage.style.display = 'none';
            }, 5000);
        }
    }

    function setLoadingState(loading) {
        if (loading) {
            loadingSpinner.style.display = 'block';
            document.body.classList.add('loading');
            extractBtn.disabled = true;
            extractBtn.innerHTML = '<span>🔄 Processing...</span>';
        } else {
            loadingSpinner.style.display = 'none';
            document.body.classList.remove('loading');
            extractBtn.disabled = false;
            extractBtn.innerHTML = '<span>Extract Dates</span>';
        }
    }

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

    function checkUrlParams() {
        const urlParams = new URLSearchParams(window.location.search);
        const authStatus = urlParams.get('auth');
        
        if (authStatus === 'success') {
            showStatus('Successfully connected to Google Calendar!', 'success');
            connectCalendarBtn.innerHTML = '<span>✅ Connected to Google Calendar</span>';
            connectCalendarBtn.disabled = true;
            window.history.replaceState({}, document.title, window.location.pathname);
        } else if (authStatus === 'error') {
            showStatus('Failed to connect to Google Calendar. Please try again.', 'error');
            window.history.replaceState({}, document.title, window.location.pathname);
        }
    }

    // Initialize
    checkUrlParams();
});