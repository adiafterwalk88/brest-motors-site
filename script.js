// ===== Конфигурация Supabase =====
// Замените на свои данные из настроек Supabase (Settings > API)
const SUPABASE_URL = 'https://ваш-проект.supabase.co';
const SUPABASE_ANON_KEY = 'ваш-anon-публичный-ключ';

// Инициализация Supabase
const supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// ===== DOM элементы =====
const authSection = document.getElementById('authSection');
const ordersSection = document.getElementById('ordersSection');
const authForm = document.getElementById('authForm');
const registerForm = document.getElementById('registerForm');
const authEmail = document.getElementById('authEmail');
const authPassword = document.getElementById('authPassword');
const regEmail = document.getElementById('regEmail');
const regPassword = document.getElementById('regPassword');
const authError = document.getElementById('authError');
const regError = document.getElementById('regError');
const userInfo = document.getElementById('userInfo');
const logoutBtn = document.getElementById('logoutBtn');
const ordersList = document.getElementById('ordersList');
const searchInput = document.getElementById('searchInput');
const statusFilter = document.getElementById('statusFilter');
const pagination = document.getElementById('pagination');
const createOrderBtn = document.getElementById('createOrderBtn');
const orderModal = document.getElementById('orderModal');
const deleteModal = document.getElementById('deleteModal');
const orderForm = document.getElementById('orderForm');
const orderId = document.getElementById('orderId');
const orderNumber = document.getElementById('orderNumber');
const clientName = document.getElementById('clientName');
const orderAmount = document.getElementById('orderAmount');
const orderStatus = document.getElementById('orderStatus');
const orderDescription = document.getElementById('orderDescription');
const modalTitle = document.getElementById('modalTitle');
const deleteOrderNumber = document.getElementById('deleteOrderNumber');
const showRegister = document.getElementById('showRegister');
const showLogin = document.getElementById('showLogin');

// ===== Состояние =====
let currentUser = null;
let orders = [];
let currentPage = 1;
const pageSize = 9;
let totalOrders = 0;
let deleteTargetId = null;

// ===== Проверка сессии при загрузке =====
async function checkSession() {
    const { data: { session } } = await supabase.auth.getSession();
    if (session) {
        currentUser = session.user;
        showOrdersSection();
        loadOrders();
    } else {
        showAuthSection();
    }
}

// ===== Переключение между секциями =====
function showAuthSection() {
    authSection.style.display = 'flex';
    ordersSection.style.display = 'none';
    authForm.style.display = 'block';
    registerForm.style.display = 'none';
    userInfo.textContent = '';
    logoutBtn.style.display = 'none';
}

function showOrdersSection() {
    authSection.style.display = 'none';
    ordersSection.style.display = 'block';
    userInfo.textContent = currentUser?.email || '';
    logoutBtn.style.display = 'inline-flex';
}

// ===== Авторизация =====
authForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    authError.textContent = '';
    const email = authEmail.value.trim();
    const password = authPassword.value.trim();

    const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password
    });

    if (error) {
        authError.textContent = error.message;
        return;
    }

    currentUser = data.user;
    showOrdersSection();
    loadOrders();
    authForm.reset();
});

// ===== Регистрация =====
registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    regError.textContent = '';
    const email = regEmail.value.trim();
    const password = regPassword.value.trim();

    if (password.length < 6) {
        regError.textContent = 'Пароль должен быть минимум 6 символов';
        return;
    }

    const { data, error } = await supabase.auth.signUp({
        email,
        password
    });

    if (error) {
        regError.textContent = error.message;
        return;
    }

    if (data.user) {
        regError.textContent = '✅ Регистрация успешна! Теперь войдите.';
        registerForm.style.display = 'none';
        authForm.style.display = 'block';
        authEmail.value = email;
        authPassword.value = '';
        regEmail.value = '';
        regPassword.value = '';
        authError.textContent = '';
    }
});

// ===== Выход =====
logoutBtn.addEventListener('click', async () => {
    await supabase.auth.signOut();
    currentUser = null;
    orders = [];
    showAuthSection();
    ordersList.innerHTML = '';
    pagination.innerHTML = '';
});

// ===== Переключение форм =====
showRegister.addEventListener('click', (e) => {
    e.preventDefault();
    authForm.style.display = 'none';
    registerForm.style.display = 'block';
    authError.textContent = '';
    regError.textContent = '';
});

showLogin.addEventListener('click', (e) => {
    e.preventDefault();
    registerForm.style.display = 'none';
    authForm.style.display = 'block';
    regError.textContent = '';
    authError.textContent = '';
});

// ===== Загрузка заказов =====
async function loadOrders() {
    if (!currentUser) return;

    const search = searchInput.value.trim();
    const status = statusFilter.value;

    let query = supabase
        .from('orders')
        .select('*', { count: 'exact' })
        .eq('user_id', currentUser.id)
        .order('created_at', { ascending: false });

    if (search) {
        query = query.or(`order_number.ilike.%${search}%,client_name.ilike.%${search}%`);
    }

    if (status !== 'all') {
        query = query.eq('status', status);
    }

    const from = (currentPage - 1) * pageSize;
    const to = from + pageSize - 1;
    query = query.range(from, to);

    const { data, error, count } = await query;

    if (error) {
        console.error('Ошибка загрузки заказов:', error);
        return;
    }

    orders = data || [];
    totalOrders = count || 0;
    renderOrders();
    renderPagination();
}

// ===== Рендер заказов =====
function renderOrders() {
    if (orders.length === 0) {
        ordersList.innerHTML = `
            <div class="empty-state" style="grid-column: 1 / -1;">
                <i class="fas fa-inbox"></i>
                <h3>Нет заказов</h3>
                <p>Создайте первый заказ, нажав кнопку "Создать заказ"</p>
            </div>
        `;
        return;
    }

    ordersList.innerHTML = orders.map(order => `
        <div class="order-card">
            <div class="order-number">${order.order_number}</div>
            <div class="order-client"><i class="fas fa-user"></i> ${order.client_name}</div>
            <div class="order-amount">${Number(order.amount).toLocaleString()} <small>₽</small></div>
            <span class="order-status status-${order.status.replace(/ /g, '-')}">${order.status}</span>
            ${order.description ? `<p style="margin-top:8px;font-size:13px;color:#666;">${order.description}</p>` : ''}
            <div class="order-meta">
                <span class="order-date"><i class="far fa-calendar-alt"></i> ${new Date(order.created_at).toLocaleDateString()}</span>
                <div class="order-actions">
                    <button class="edit-btn" data-id="${order.id}" title="Редактировать">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="delete-btn" data-id="${order.id}" data-number="${order.order_number}" title="Удалить">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        </div>
    `).join('');

    // Обработчики для кнопок редактирования
    document.querySelectorAll('.edit-btn').forEach(btn => {
        btn.addEventListener('click', () => openEditModal(btn.dataset.id));
    });

    // Обработчики для кнопок удаления
    document.querySelectorAll('.delete-btn').forEach(btn => {
        btn.addEventListener('click', () => openDeleteModal(btn.dataset.id, btn.dataset.number));
    });
}

// ===== Пагинация =====
function renderPagination() {
    const totalPages = Math.ceil(totalOrders / pageSize);
    pagination.innerHTML = '';

    if (totalPages <= 1) return;

    const prevBtn = document.createElement('button');
    prevBtn.innerHTML = '<i class="fas fa-chevron-left"></i>';
    prevBtn.disabled = currentPage === 1;
    prevBtn.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            loadOrders();
        }
    });
    pagination.appendChild(prevBtn);

    for (let i = 1; i <= totalPages; i++) {
        const btn = document.createElement('button');
        btn.textContent = i;
        if (i === currentPage) btn.classList.add('active');
        btn.addEventListener('click', () => {
            currentPage = i;
            loadOrders();
        });
        pagination.appendChild(btn);
    }

    const nextBtn = document.createElement('button');
    nextBtn.innerHTML = '<i class="fas fa-chevron-right"></i>';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.addEventListener('click', () => {
        if (currentPage < totalPages) {
            currentPage++;
            loadOrders();
        }
    });
    pagination.appendChild(nextBtn);
}

// ===== Создание заказа =====
createOrderBtn.addEventListener('click', () => {
    orderId.value = '';
    orderNumber.value = '';
    clientName.value = '';
    orderAmount.value = '';
    orderStatus.value = 'новый';
    orderDescription.value = '';
    modalTitle.innerHTML = '<i class="fas fa-plus-circle"></i> Создание заказа';
    orderModal.style.display = 'flex';
});

// ===== Редактирование заказа =====
async function openEditModal(id) {
    const { data, error } = await supabase
        .from('orders')
        .select('*')
        .eq('id', id)
        .single();

    if (error) {
        console.error('Ошибка загрузки заказа:', error);
        return;
    }

    orderId.value = data.id;
    orderNumber.value = data.order_number;
    clientName.value = data.client_name;
    orderAmount.value = data.amount;
    orderStatus.value = data.status;
    orderDescription.value = data.description || '';
    modalTitle.innerHTML = '<i class="fas fa-edit"></i> Редактирование заказа';
    orderModal.style.display = 'flex';
}

// ===== Сохранение заказа =====
orderForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const id = orderId.value;
    const data = {
        order_number: orderNumber.value.trim(),
        client_name: clientName.value.trim(),
        amount: parseFloat(orderAmount.value),
        status: orderStatus.value,
        description: orderDescription.value.trim(),
        user_id: currentUser.id
    };

    let result;

    if (id) {
        // Обновление
        result = await supabase
            .from('orders')
            .update(data)
            .eq('id', id)
            .eq('user_id', currentUser.id);
    } else {
        // Создание
        result = await supabase
            .from('orders')
            .insert([data]);
    }

    if (result.error) {
        alert('Ошибка сохранения: ' + result.error.message);
        return;
    }

    orderModal.style.display = 'none';
    orderForm.reset();
    loadOrders();
});

// ===== Удаление заказа =====
function openDeleteModal(id, number) {
    deleteTargetId = id;
    deleteOrderNumber.textContent = number;
    deleteModal.style.display = 'flex';
}

document.getElementById('confirmDeleteBtn').addEventListener('click', async () => {
    if (!deleteTargetId) return;

    const { error } = await supabase
        .from('orders')
        .delete()
        .eq('id', deleteTargetId)
        .eq('user_id', currentUser.id);

    if (error) {
        alert('Ошибка удаления: ' + error.message);
        return;
    }

    deleteModal.style.display = 'none';
    deleteTargetId = null;
    loadOrders();
});

document.getElementById('cancelDeleteBtn').addEventListener('click', () => {
    deleteModal.style.display = 'none';
    deleteTargetId = null;
});

// ===== Закрытие модалок =====
document.querySelectorAll('.modal-close').forEach(close => {
    close.addEventListener('click', () => {
        orderModal.style.display = 'none';
        deleteModal.style.display = 'none';
    });
});

document.getElementById('cancelModalBtn').addEventListener('click', () => {
    orderModal.style.display = 'none';
});

window.addEventListener('click', (e) => {
    if (e.target === orderModal) orderModal.style.display = 'none';
    if (e.target === deleteModal) deleteModal.style.display = 'none';
});

// ===== Поиск и фильтр =====
searchInput.addEventListener('input', debounce(() => {
    currentPage = 1;
    loadOrders();
}, 400));

statusFilter.addEventListener('change', () => {
    currentPage = 1;
    loadOrders();
});

// ===== Debounce =====
function debounce(fn, delay) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

// ===== Запуск =====
checkSession();

// ===== Обработка изменений авторизации в реальном времени =====
supabase.auth.onAuthStateChange((event, session) => {
    if (event === 'SIGNED_OUT') {
        currentUser = null;
        showAuthSection();
        ordersList.innerHTML = '';
        pagination.innerHTML = '';
    }
});
