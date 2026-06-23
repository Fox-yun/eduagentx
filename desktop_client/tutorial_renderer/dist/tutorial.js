// Utility for HTML escaping
function escapeHtml(unsafe) {
    return (unsafe || '').replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function shuffle(array) {
    let currentIndex = array.length, randomIndex;
    while (currentIndex !== 0) {
        randomIndex = Math.floor(Math.random() * currentIndex);
        currentIndex--;
        [array[currentIndex], array[randomIndex]] = [array[randomIndex], array[currentIndex]];
    }
    return array;
}

// State Management
const StateManager = {
    buildKey(payload, widgetId) {
        return ["eduagentx", "tutorial", payload.task_id || "unknown", widgetId].join(":");
    },
    loadState(key, widgetSignature) {
        try {
            const stored = localStorage.getItem(key);
            if (stored) {
                const parsed = JSON.parse(stored);
                if (parsed.widgetSignature === widgetSignature) {
                    return parsed.state;
                }
            }
        } catch (e) {
            console.error("Failed to load state", e);
        }
        return null;
    },
    saveState(key, widgetSignature, state) {
        try {
            localStorage.setItem(key, JSON.stringify({
                widgetSignature,
                state
            }));
        } catch (e) {
            console.error("Failed to save state", e);
        }
    }
};

// Renderers
const widgetRenderers = {
    inline_quiz: renderInlineQuiz,
    sequence_sort: renderSequenceSort,
    matching_pairs: renderMatchingPairs,
    stepper_tutorial: renderStepperTutorial
};

function renderInlineQuiz(widget, payload, container) {
    const stateKey = StateManager.buildKey(payload, widget.widget_id);
    const widgetSignature = JSON.stringify(widget); // simple sig
    let state = StateManager.loadState(stateKey, widgetSignature) || {
        selectedOptionId: null,
        submitted: false,
        correct: false,
        attempts: 0
    };

    let html = `
        <div class="quiz-container" id="quiz-${widget.widget_id}">
            <div class="question" style="margin-bottom:12px;"><strong>${escapeHtml(widget.question)}</strong></div>
            <div class="options">
    `;
    widget.options.forEach(opt => {
        const isChecked = state.selectedOptionId === opt.option_id ? "checked" : "";
        const isDisabled = (state.submitted && state.correct) ? "disabled" : "";
        html += `
            <div class="quiz-option">
                <label>
                    <input type="radio" name="q-${widget.widget_id}" value="${escapeHtml(opt.option_id)}" ${isChecked} ${isDisabled}>
                    ${escapeHtml(opt.text)}
                </label>
            </div>
        `;
    });
    
    html += `
            </div>
            <button class="btn" id="btn-${widget.widget_id}" ${state.submitted && state.correct ? 'disabled' : ''}>提交答案</button>
            <div id="feedback-${widget.widget_id}" class="quiz-feedback ${state.submitted ? (state.correct ? 'success' : 'error') : ''}" style="display: ${state.submitted ? 'block' : 'none'}">
                <div class="msg"><strong>${state.correct ? '回答正确！' : '回答错误，请重试。'}</strong></div>
                ${state.submitted && state.correct ? `<div class="exp" style="margin-top:8px; font-size:0.9em;">${escapeHtml(widget.explanation || '')}</div>` : ''}
            </div>
        </div>
    `;
    container.innerHTML = html;

    const submitBtn = container.querySelector(`#btn-${widget.widget_id}`);
    submitBtn.addEventListener('click', () => {
        const selected = container.querySelector(`input[name="q-${widget.widget_id}"]:checked`);
        if (!selected) {
            alert("请先选择一个答案。");
            return;
        }
        state.selectedOptionId = selected.value;
        state.submitted = true;
        state.attempts += 1;
        state.correct = (selected.value === widget.correct_option_id);
        
        StateManager.saveState(stateKey, widgetSignature, state);
        renderInlineQuiz(widget, payload, container); // re-render
    });
}

function renderSequenceSort(widget, payload, container) {
    const stateKey = StateManager.buildKey(payload, widget.widget_id);
    const widgetSignature = JSON.stringify(widget);
    let state = StateManager.loadState(stateKey, widgetSignature);
    
    if (!state) {
        let initialOrder = shuffle([...widget.items]).map(i => i.item_id);
        state = {
            order: initialOrder,
            attempts: 0,
            completed: false
        };
        StateManager.saveState(stateKey, widgetSignature, state);
    }

    const orderMap = {};
    widget.items.forEach(i => { orderMap[i.item_id] = i.text; });

    let html = `<ul class="sortable-list" id="sort-${widget.widget_id}">`;
    state.order.forEach((itemId, idx) => {
        const text = orderMap[itemId] || itemId;
        html += `
            <li class="sortable-item" data-id="${escapeHtml(itemId)}" draggable="${!state.completed}">
                <span>${escapeHtml(text)}</span>
                <div class="sort-actions">
                    <button class="btn btn-secondary move-up" data-idx="${idx}" ${idx === 0 || state.completed ? 'disabled' : ''}>↑</button>
                    <button class="btn btn-secondary move-down" data-idx="${idx}" ${idx === state.order.length - 1 || state.completed ? 'disabled' : ''}>↓</button>
                </div>
            </li>
        `;
    });
    html += `</ul>
        <button class="btn" id="btn-${widget.widget_id}" style="margin-top:16px;" ${state.completed ? 'disabled' : ''}>验证排序</button>
        <div id="feedback-${widget.widget_id}" class="sort-feedback sort-success" style="display: ${state.completed ? 'block' : 'none'}">
            ${escapeHtml(widget.success_message || '排序正确！')}
        </div>
    `;
    container.innerHTML = html;

    const list = container.querySelector(`#sort-${widget.widget_id}`);
    
    // Move up/down logic
    container.querySelectorAll('.move-up').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const idx = parseInt(e.target.getAttribute('data-idx'));
            if (idx > 0) {
                [state.order[idx-1], state.order[idx]] = [state.order[idx], state.order[idx-1]];
                StateManager.saveState(stateKey, widgetSignature, state);
                renderSequenceSort(widget, payload, container);
            }
        });
    });
    container.querySelectorAll('.move-down').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const idx = parseInt(e.target.getAttribute('data-idx'));
            if (idx < state.order.length - 1) {
                [state.order[idx], state.order[idx+1]] = [state.order[idx+1], state.order[idx]];
                StateManager.saveState(stateKey, widgetSignature, state);
                renderSequenceSort(widget, payload, container);
            }
        });
    });

    // Drag and Drop
    let draggedItem = null;
    list.addEventListener('dragstart', e => {
        if (state.completed) return;
        draggedItem = e.target.closest('.sortable-item');
        e.dataTransfer.effectAllowed = 'move';
    });
    list.addEventListener('dragover', e => {
        if (state.completed) return;
        e.preventDefault();
        const targetItem = e.target.closest('.sortable-item');
        if (targetItem && targetItem !== draggedItem) {
            const rect = targetItem.getBoundingClientRect();
            const next = (e.clientY - rect.top) / (rect.bottom - rect.top) > 0.5;
            list.insertBefore(draggedItem, next ? targetItem.nextSibling : targetItem);
        }
    });
    list.addEventListener('dragend', e => {
        if (state.completed) return;
        const newOrder = Array.from(list.querySelectorAll('.sortable-item')).map(el => el.getAttribute('data-id'));
        state.order = newOrder;
        StateManager.saveState(stateKey, widgetSignature, state);
        renderSequenceSort(widget, payload, container);
    });

    // Submit
    const btn = container.querySelector(`#btn-${widget.widget_id}`);
    btn.addEventListener('click', () => {
        state.attempts++;
        const isCorrect = state.order.every((val, index) => val === widget.correct_order[index]);
        if (isCorrect) {
            state.completed = true;
            StateManager.saveState(stateKey, widgetSignature, state);
            renderSequenceSort(widget, payload, container);
        } else {
            const feedback = container.querySelector(`#feedback-${widget.widget_id}`);
            feedback.style.display = 'block';
            feedback.style.color = '#dc2626';
            feedback.textContent = '顺序有误，请重试。';
            setTimeout(() => {
                if(!state.completed) feedback.style.display = 'none';
            }, 2000);
        }
    });
}

function renderMatchingPairs(widget, payload, container) {
    const stateKey = StateManager.buildKey(payload, widget.widget_id);
    const widgetSignature = JSON.stringify(widget);
    let state = StateManager.loadState(stateKey, widgetSignature);

    if (!state) {
        const leftItems = shuffle(widget.pairs.map((p, idx) => {
            const isObj = typeof p.left === 'object';
            return {
                id: p.pair_id || `pair_${idx}`, 
                item_id: isObj ? p.left.item_id : `left_${idx}`, 
                text: isObj ? p.left.text : p.left, 
                side: 'left'
            };
        }));
        const rightItems = shuffle(widget.pairs.map((p, idx) => {
            const isObj = typeof p.right === 'object';
            return {
                id: p.pair_id || `pair_${idx}`, 
                item_id: isObj ? p.right.item_id : `right_${idx}`, 
                text: isObj ? p.right.text : p.right, 
                side: 'right'
            };
        }));
        state = {
            leftItems,
            rightItems,
            selectedLeftId: null,
            selectedRightId: null,
            matchedPairIds: [],
            attempts: 0,
            completed: false
        };
        StateManager.saveState(stateKey, widgetSignature, state);
    }

    const renderCard = (item) => {
        const isMatched = state.matchedPairIds.includes(item.id);
        const isSelected = state.selectedLeftId === item.id || state.selectedRightId === item.id;
        const classes = `matching-card ${isMatched ? 'matched' : ''} ${isSelected ? 'selected' : ''}`;
        return `<div class="${classes}" data-id="${escapeHtml(item.id)}" data-side="${item.side}">
            ${escapeHtml(item.text)}
            ${isMatched ? ' ✅' : ''}
        </div>`;
    };

    let html = `
        <div class="matching-container" id="match-${widget.widget_id}">
            <div class="matching-col left-col">
                ${state.leftItems.map(renderCard).join('')}
            </div>
            <div class="matching-col right-col">
                ${state.rightItems.map(renderCard).join('')}
            </div>
        </div>
        <div id="feedback-${widget.widget_id}" class="matching-feedback" style="display: ${state.completed ? 'block' : 'none'}">
            全部匹配正确！
        </div>
    `;
    container.innerHTML = html;

    const cards = container.querySelectorAll('.matching-card:not(.matched)');
    cards.forEach(card => {
        card.addEventListener('click', () => {
            if (state.completed) return;
            const side = card.getAttribute('data-side');
            const id = card.getAttribute('data-id');

            if (side === 'left') {
                state.selectedLeftId = id;
            } else {
                state.selectedRightId = id;
            }

            if (state.selectedLeftId && state.selectedRightId) {
                state.attempts++;
                if (state.selectedLeftId === state.selectedRightId) {
                    // Match!
                    state.matchedPairIds.push(state.selectedLeftId);
                    state.selectedLeftId = null;
                    state.selectedRightId = null;
                    if (state.matchedPairIds.length === widget.pairs.length) {
                        state.completed = true;
                    }
                    StateManager.saveState(stateKey, widgetSignature, state);
                    renderMatchingPairs(widget, payload, container);
                } else {
                    // Error
                    const leftCard = container.querySelector(`.left-col .matching-card[data-id="${state.selectedLeftId}"]`);
                    const rightCard = container.querySelector(`.right-col .matching-card[data-id="${state.selectedRightId}"]`);
                    leftCard.classList.add('error');
                    rightCard.classList.add('error');
                    
                    state.selectedLeftId = null;
                    state.selectedRightId = null;
                    StateManager.saveState(stateKey, widgetSignature, state);
                    
                    setTimeout(() => {
                        renderMatchingPairs(widget, payload, container);
                    }, 500);
                }
            } else {
                StateManager.saveState(stateKey, widgetSignature, state);
                renderMatchingPairs(widget, payload, container);
            }
        });
    });
}

function renderStepperTutorial(widget, payload, container) {
    const stateKey = StateManager.buildKey(payload, widget.widget_id);
    const widgetSignature = JSON.stringify(widget);
    let state = StateManager.loadState(stateKey, widgetSignature) || {
        currentStep: 0,
        hintExpanded: false,
        completed: false
    };

    const step = widget.steps[state.currentStep];
    const isFirst = state.currentStep === 0;
    const isLast = state.currentStep === widget.steps.length - 1;

    let html = `
        <div class="stepper-header">步骤进度：${state.currentStep + 1} / ${widget.steps.length}</div>
        <div class="stepper-content">
            <h4 style="margin-top:0;">${escapeHtml(step.title)}</h4>
            <div>${escapeHtml(step.content)}</div>
        </div>
        ${step.hint ? `
        <div class="stepper-hint" style="display: ${state.hintExpanded ? 'block' : 'none'};">
            ${escapeHtml(step.hint)}
        </div>
        ` : ''}
        <div class="stepper-actions">
            <div class="left-actions">
                <button class="btn btn-secondary" id="prev-${widget.widget_id}" ${isFirst ? 'disabled' : ''}>上一步</button>
                ${step.hint ? `<button class="btn btn-secondary" id="hint-${widget.widget_id}">💡 ${state.hintExpanded ? '隐藏提示' : '查看提示'}</button>` : ''}
            </div>
            <button class="btn" id="next-${widget.widget_id}">${isLast ? (state.completed ? '已完成' : '完成') : '下一步'}</button>
        </div>
    `;
    container.innerHTML = html;

    const prevBtn = container.querySelector(`#prev-${widget.widget_id}`);
    const nextBtn = container.querySelector(`#next-${widget.widget_id}`);
    const hintBtn = container.querySelector(`#hint-${widget.widget_id}`);

    if (prevBtn) prevBtn.addEventListener('click', () => {
        if (!isFirst) {
            state.currentStep--;
            state.hintExpanded = false;
            StateManager.saveState(stateKey, widgetSignature, state);
            renderStepperTutorial(widget, payload, container);
        }
    });

    if (nextBtn) nextBtn.addEventListener('click', () => {
        if (!isLast) {
            state.currentStep++;
            state.hintExpanded = false;
            StateManager.saveState(stateKey, widgetSignature, state);
            renderStepperTutorial(widget, payload, container);
        } else {
            state.completed = true;
            StateManager.saveState(stateKey, widgetSignature, state);
            renderStepperTutorial(widget, payload, container);
        }
    });

    if (hintBtn) hintBtn.addEventListener('click', () => {
        state.hintExpanded = !state.hintExpanded;
        StateManager.saveState(stateKey, widgetSignature, state);
        renderStepperTutorial(widget, payload, container);
    });
}

function renderWidgetError(widget, container) {
    container.innerHTML = `<div style="color:red; padding:10px; border:1px solid red; border-radius:4px;">组件渲染失败: ${escapeHtml(widget.type)}</div>`;
}

// Main Window Controller
window.eduTutorial = {
    renderBase64(payloadBase64) {
        try {
            const binary = atob(payloadBase64);
            const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
            const jsonText = new TextDecoder("utf-8").decode(bytes);
            const payload = JSON.parse(jsonText);
            this.render(payload);
        } catch (e) {
            console.error("Failed to parse payload", e);
        }
    },
    render(payload) {
        const container = document.getElementById('content');
        container.innerHTML = '';
        
        // Render Markdown
        if (payload.markdown) {
            const mdDiv = document.createElement('div');
            if (window.marked) {
                mdDiv.innerHTML = marked.parse(payload.markdown, { headerIds: false, mangle: false });
            } else {
                mdDiv.textContent = payload.markdown;
            }
            container.appendChild(mdDiv);
        }
        
        // Render Widgets
        if (payload.widgets && payload.widgets.length > 0) {
            const widgetsDiv = document.createElement('div');
            widgetsDiv.innerHTML = '<hr><h2>互动练习</h2>';
            
            payload.widgets.forEach(widget => {
                const wrapper = document.createElement('div');
                wrapper.className = 'widget-container';
                
                let headerHtml = `
                    <h3 class="widget-title">${escapeHtml(widget.title)}</h3>
                    <div class="widget-instruction">${escapeHtml(widget.instruction || '')}</div>
                `;
                
                const headerDiv = document.createElement('div');
                headerDiv.innerHTML = headerHtml;
                wrapper.appendChild(headerDiv);

                const widgetContent = document.createElement('div');
                wrapper.appendChild(widgetContent);

                const renderer = widgetRenderers[widget.type];
                if (renderer) {
                    try {
                        renderer(widget, payload, widgetContent);
                    } catch(e) {
                        console.error(e);
                        renderWidgetError(widget, widgetContent);
                    }
                } else {
                    widgetContent.innerHTML = `<div><em>[${escapeHtml(widget.type)} 组件不支持]</em></div>`;
                }

                widgetsDiv.appendChild(wrapper);
            });
            container.appendChild(widgetsDiv);
        }
    }
};

// Check for pending payload
if (window._pendingTutorialPayload) {
    window.eduTutorial.renderBase64(window._pendingTutorialPayload);
    delete window._pendingTutorialPayload;
}
