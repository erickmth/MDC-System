// on.js - Impede que a tela do dispositivo desligue
// Coloque este arquivo no mesmo diretório dos seus arquivos HTML

// Função para ativar a Wake Lock
async function activateWakeLock() {
    try {
        // Verifica se a API está disponível no navegador
        if ('wakeLock' in navigator) {
            const wakeLock = await navigator.wakeLock.request('screen');
            
            // Listen for when the wake lock is released
            wakeLock.addEventListener('release', () => {
                console.log('Screen Wake Lock released:', wakeLock.released);
            });
            
            console.log('Screen Wake Lock activado - Tela manterá ligada');
            return wakeLock;
        } else {
            console.warn('Screen Wake Lock API não suportada neste navegador');
            showWakeLockMessage();
            return null;
        }
    } catch (err) {
        console.error(`${err.name}, ${err.message}`);
        showWakeLockMessage();
        return null;
    }
}

// Mostrar mensagem sobre Wake Lock não suportado
function showWakeLockMessage() {
    // Verifica se já existe uma mensagem na página
    if (!document.getElementById('wakeLockMessage')) {
        const message = document.createElement('div');
        message.id = 'wakeLockMessage';
        message.style.position = 'fixed';
        message.style.bottom = '10px';
        message.style.right = '10px';
        message.style.padding = '10px';
        message.style.backgroundColor = '#ffecb3';
        message.style.border = '1px solid #ffd54f';
        message.style.borderRadius = '4px';
        message.style.zIndex = '1000';
        message.style.fontSize = '14px';
        message.innerHTML = '⚠️ Seu navegador não suporta bloqueio de tela. Para evitar que a tela desligue, ajuste as configurações de energia do dispositivo.';
        
        document.body.appendChild(message);
        
        // Remover a mensagem após 10 segundos
        setTimeout(() => {
            if (document.getElementById('wakeLockMessage')) {
                document.body.removeChild(message);
            }
        }, 10000);
    }
}

// Ativar a Wake Lock quando a página carregar
document.addEventListener('DOMContentLoaded', async () => {
    let wakeLock = null;
    
    // Ativar wake lock
    wakeLock = await activateWakeLock();
    
    // Reativar wake lock quando a página ficar visível novamente
    document.addEventListener('visibilitychange', async () => {
        if (wakeLock !== null && document.visibilityState === 'visible') {
            wakeLock = await activateWakeLock();
        }
    });
});

// Exportar para uso em outros scripts (se necessário)
window.screenWakeLock = {
    activate: activateWakeLock
};