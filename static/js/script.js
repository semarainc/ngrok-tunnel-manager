// Global variables
let tunnelsTable;
let apikeysTable;
let confirmCallback = null;
let toast;

// View Logs Handler
$(document).on('click', '.view-logs', function() {
    const id = $(this).data('id');

    $.ajax({
        url: `/api/tunnels/${id}/log`,
        type: 'GET',
        success: function(response) {
            if (response.success) {
                $('#logsAppName').text(response.app_name);
                $('#logsContent').text(response.log_content);
                $('#logsModal').modal('show');
            } else {
                showToast('Error', response.message, 'error');
            }
        },
        error: handleApiError
    });
});

$(document).ready(function() {
    // Initialize Bootstrap toast
    toast = new bootstrap.Toast(document.getElementById('toast'));

    // Initialize DataTables
    tunnelsTable = $('#tunnelsTable').DataTable({
        responsive: true,
        columns: [
            { data: 'app_name' },
            { data: 'local_addr' },
            { data: 'tunnel_type' },
            { data: 'api_key_name' },
            {
                data: 'time_limit',
                render: function(data) {
                    return data == 0 ? 'Forever' : data + ' Hours';
                }
            },
            { data: 'remaining_time' },
            {
                data: 'status',
                className: 'tunnel-status',
                render: function(data) {
                    let statusClass = '';
                    switch(data) {
                        case 'running':
                            statusClass = 'status-running';
                            break;
                        case 'stopped':
                            statusClass = 'status-stopped';
                            break;
                        case 'time_expired':
                            statusClass = 'status-time_expired';
                            break;
                    }
                    return '<span class="' + statusClass + '">' + data + '</span>';
                }
            },
            {
                data: 'public_url',
                className: 'public-url',
                render: function(data) {
                    if (data) {
                        return '<a href="' + data + '" target="_blank">' + data + '</a>';
                    }
                    return '';
                }
            },
            {
                data: null,
                orderable: false,
                className: 'tunnel-actions',
                render: function(data, type, row) {
                    let actionButtons = '';

                    // Start/Stop button
                    if (row.status === 'running') {
                        actionButtons += '<button class="btn btn-danger btn-sm btn-action stop-tunnel" data-id="' + row.id + '" title="Stop"><i class="fas fa-stop"></i></button>';
                    } else {
                        actionButtons += '<button class="btn btn-success btn-sm btn-action start-tunnel" data-id="' + row.id + '" title="Start"><i class="fas fa-play"></i></button>';
                    }

                    // Restart button (only for running tunnels)
                    if (row.status === 'running') {
                        actionButtons += '<button class="btn btn-warning btn-sm btn-action restart-tunnel" data-id="' + row.id + '" title="Restart"><i class="fas fa-sync"></i></button>';
                    }

                    // Edit and Delete buttons
                    actionButtons += '<button class="btn btn-primary btn-sm btn-action edit-tunnel" data-bs-toggle="modal" data-bs-target="#tunnelModal" data-id="' + row.id + '" title="Edit"><i class="fas fa-edit"></i></button>';
                    actionButtons += '<button class="btn btn-danger btn-sm btn-action delete-tunnel" data-id="' + row.id + '" title="Delete"><i class="fas fa-trash"></i></button>';
                    actionButtons += '<button class="btn btn-info btn-sm btn-action view-logs" data-id="' + row.id + '" title="View Logs" ' + (row.has_logs ? '' : 'disabled') + '><i class="fas fa-scroll"></i></button>';

                    return actionButtons;
                }
            }
        ],
        columnDefs: [
            { targets: -1, orderable: false }  // Non-aktifkan sorting untuk kolom terakhir
        ]
    });

    apikeysTable = $('#apikeysTable').DataTable({
        responsive: true,
        columns: [
            { data: 'name' },
            {
                data: 'api_key',
                render: function(data) {
                    // Show first 10 chars and rest as asterisks
                    if (data) {
                        const visible = data.substring(0, 10);
                        const masked = '*'.repeat(Math.max(0, data.length - 10));
                        return visible + masked;
                    }
                    return '';
                }
            },
            {
                data: null,
                orderable: false,
                render: function(data, type, row) {
                    return '<button class="btn btn-primary btn-sm edit-apikey" data-bs-toggle="modal" data-bs-target="#apikeyModal" data-id="' + row.id + '"><i class="fas fa-edit"></i></button> ' +
                    '<button class="btn btn-danger btn-sm delete-apikey" data-id="' + row.id + '"><i class="fas fa-trash"></i></button>';
                }
            }
        ]
    });

    // Load initial data
    loadTunnels();
    loadApiKeys();

    // Set up refresh interval (every 30 seconds)
    setInterval(function() {
        loadTunnels();
    }, 30000);

    // Setup event handlers
    setupTunnelEventHandlers();
    setupApiKeyEventHandlers();
});

// Function to display notification toast
function showToast(title, message, type = 'success') {
    $('#toastTitle').text(title);
    $('#toastMessage').text(message);

    // Remove existing classes and add new class based on type
    const toastElement = document.getElementById('toast');
    toastElement.classList.remove('bg-success', 'bg-danger', 'bg-warning', 'text-white');

    if (type === 'success') {
        toastElement.classList.add('bg-success', 'text-white');
    } else if (type === 'error') {
        toastElement.classList.add('bg-danger', 'text-white');
    } else if (type === 'warning') {
        toastElement.classList.add('bg-warning');
    }

    toast.show();
}

// Function to handle API errors
function handleApiError(xhr, status, error) {
    try {
        const response = JSON.parse(xhr.responseText);
        showToast('Error', response.message || 'An unknown error occurred', 'error');
    } catch (e) {
        showToast('Error', 'An unknown error occurred', 'error');
    }
    console.error('API Error:', error, xhr.responseText);
}

// Function to load tunnels
function loadTunnels() {
    $.ajax({
        url: '/api/tunnels',
        type: 'GET',
        dataType: 'json',
        success: function(data) {
            tunnelsTable.clear().rows.add(data).draw();
        },
        error: handleApiError
    });
}

// Function to load API keys for dropdown
function loadApiKeysDropdown() {
    return $.ajax({
        url: '/api/apikeys',
        type: 'GET',
        dataType: 'json',
        success: function(data) {
            const select = $('#apiKeyName');
            select.empty();

            if (data.length === 0) {
                select.append($('<option>', {
                    value: '',
                    text: 'No API keys available - add one first'
                }));
            } else {
                data.forEach(function(item) {
                    select.append($('<option>', {
                        value: item.name,
                        text: item.name
                    }));
                });
            }
        },
        error: handleApiError
    });
}

// Function to load API keys
function loadApiKeys() {
    $.ajax({
        url: '/api/apikeys/full',
        type: 'GET',
        dataType: 'json',
        success: function(data) {
            apikeysTable.clear().rows.add(data).draw();
        },
        error: handleApiError
    });

    // Also refresh the dropdown
    loadApiKeysDropdown();
}

// Function to set up tunnel event handlers
function setupTunnelEventHandlers() {
    // Di dalam event handler tunnelModal show.bs.modal
    $('#tunnelModal').on('show.bs.modal', function(event) {
        const button = $(event.relatedTarget);
        const modal = $(this);
        const isEdit = button.hasClass('edit-tunnel');
        console.log("IsEDIT: ", isEdit);

        // Reset form
        $('#tunnelForm')[0].reset();
        $('#tunnelId').val('');

        modal.find('.modal-title').text(isEdit ? 'Edit Tunnel' : 'Add New Tunnel');

        if (isEdit) {
            const id = button.data('id');
            $('#tunnelId').val(id);

            // Ambil data dari server
            $.ajax({
                url: `/api/tunnels/${id}`,
                type: 'GET',
                success: function(tunnelData) {
                    // Isi form dengan data yang diterima
                    $('#appName').val(tunnelData.app_name);
                    $('#localAddr').val(tunnelData.local_addr);
                    $('#tunnelType').val(tunnelData.tunnel_type);
                    $('#timeLimit').val(tunnelData.time_limit);

                    // Handle API key dropdown
                    loadApiKeysDropdown().done(function() {
                        $('#apiKeyName').val(tunnelData.api_key_name);
                    });
                },
                error: handleApiError
            });
        } else {
            // Jika tambah baru, load dropdown biasa
            modal.find('.modal-title').text('Add New Tunnel');
            loadApiKeysDropdown();
        }
    });

    // Save Tunnel
    $('#saveTunnelBtn').on('click', function() {
        const tunnelId = $('#tunnelId').val();
        console.log(tunnelId);
        const tunnelData = {
            app_name: $('#appName').val(),
                           api_key_name: $('#apiKeyName').val(),
                           local_addr: $('#localAddr').val(),
                           tunnel_type: $('#tunnelType').val(),
                           time_limit: parseInt($('#timeLimit').val())
        };

        // Validate form
        if (!tunnelData.app_name || !tunnelData.api_key_name || !tunnelData.local_addr) {
            showToast('Error', 'Please fill out all required fields', 'error');
            return;
        }

        const url = tunnelId ? `/api/tunnels/${tunnelId}` : '/api/tunnels';
        const method = tunnelId ? 'PUT' : 'POST';

        $.ajax({
            url: url,
            type: method,
            contentType: 'application/json',
            data: JSON.stringify(tunnelData),
               success: function(response) {
                   $('#tunnelModal').modal('hide');
                   showToast('Success', response.message);
                   loadTunnels();
               },
               error: handleApiError
        });
    });

    // Start Tunnel
    $(document).on('click', '.start-tunnel', function() {
        const id = $(this).data('id');
        $.ajax({
            url: `/api/tunnels/${id}/start`,
            type: 'POST',
            success: function(response) {
                showToast('Success', 'Tunnel started successfully');
                loadTunnels();
            },
            error: handleApiError
        });
    });

    // Stop Tunnel
    $(document).on('click', '.stop-tunnel', function() {
        const id = $(this).data('id');
        $.ajax({
            url: `/api/tunnels/${id}/stop`,
            type: 'POST',
            success: function(response) {
                showToast('Success', 'Tunnel stopped successfully');
                loadTunnels();
            },
            error: handleApiError
        });
    });

    // Restart Tunnel
    $(document).on('click', '.restart-tunnel', function() {
        const id = $(this).data('id');
        $.ajax({
            url: `/api/tunnels/${id}/restart`,
            type: 'POST',
            success: function(response) {
                showToast('Success', 'Tunnel restarted successfully');
                loadTunnels();
            },
            error: handleApiError
        });
    });

    // Delete Tunnel
    $(document).on('click', '.delete-tunnel', function() {
        const id = $(this).data('id');
        const tunnelData = tunnelsTable.rows().data().toArray().find(t => t.id === id);

        $('#confirmMessage').text(`Are you sure you want to delete the tunnel "${tunnelData.app_name}"?`);
        $('#confirmActionBtn').text('Delete');

        confirmCallback = function() {
            $.ajax({
                url: `/api/tunnels/${id}`,
                type: 'DELETE',
                success: function(response) {
                    showToast('Success', 'Tunnel deleted successfully');
                    loadTunnels();
                },
                error: handleApiError
            });
        };

        $('#confirmModal').modal('show');
    });
}

// Function to set up API key event handlers
function setupApiKeyEventHandlers() {
    // Add/Edit API Key
    $('#apikeyModal').on('show.bs.modal', function(event) {
        const button = $(event.relatedTarget);
        const modal = $(this);
        const isEdit = button.hasClass('edit-apikey');

        // Reset form
        $('#apikeyForm')[0].reset();
        $('#apikeyId').val('');

        // Update modal title
        modal.find('.modal-title').text(isEdit ? 'Edit API Key' : 'Add New API Key');

        if (isEdit) {
            const id = button.data('id');
            $('#apikeyId').val(id);

            // Find API key data from the table
            const apiKeyData = apikeysTable.rows().data().toArray().find(k => k.id === id);
            if (apiKeyData) {
                $('#apikeyName').val(apiKeyData.name);
                $('#apikey').val(apiKeyData.api_key);
            }
        }
    });

    // Edit API Key button handler
    $(document).on('click', '.edit-apikey', function() {
        const id = $(this).data('id');

        // Find the API key data
        const apiKeyData = apikeysTable.rows().data().toArray().find(k => k.id === id);

        if (apiKeyData) {
            $('#apikeyId').val(id);
            $('#apikeyName').val(apiKeyData.name);
            $('#apikey').val(apiKeyData.api_key);
            $('#apikeyModal').modal('show');
        }
    });

    // Save API Key
    $('#saveApiKeyBtn').on('click', function() {
        const apiKeyId = $('#apikeyId').val();
        const apiKeyData = {
            name: $('#apikeyName').val(),
                           api_key: $('#apikey').val()
        };

        // Validate form
        if (!apiKeyData.name || !apiKeyData.api_key) {
            showToast('Error', 'Please fill out all required fields', 'error');
            return;
        }

        const url = apiKeyId ? `/api/apikeys/${apiKeyId}` : '/api/apikeys';
        const method = apiKeyId ? 'PUT' : 'POST';

        $.ajax({
            url: url,
            type: method,
            contentType: 'application/json',
            data: JSON.stringify(apiKeyData),
               success: function(response) {
                   $('#apikeyModal').modal('hide');
                   showToast('Success', response.message);
                   loadApiKeys();
               },
               error: handleApiError
        });
    });

    // Delete API Key
    $(document).on('click', '.delete-apikey', function() {
        const id = $(this).data('id');
        const apiKeyData = apikeysTable.rows().data().toArray().find(k => k.id === id);

        $('#confirmMessage').text(`Are you sure you want to delete the API key "${apiKeyData.name}"?`);
        $('#confirmActionBtn').text('Delete');

        confirmCallback = function() {
            $.ajax({
                url: `/api/apikeys/${id}`,
                type: 'DELETE',
                success: function(response) {
                    showToast('Success', 'API key deleted successfully');
                    loadApiKeys();
                },
                error: handleApiError
            });
        };

        $('#confirmModal').modal('show');
    });
}

// Confirmation modal action button
$('#confirmActionBtn').on('click', function() {
    if (typeof confirmCallback === 'function') {
        confirmCallback();
        confirmCallback = null;
        $('#confirmModal').modal('hide');
    }
});
