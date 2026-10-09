document.querySelector('#menu-toggle')?.addEventListener('click',()=>document.querySelector('#sidebar').classList.toggle('open'));
document.querySelectorAll('.sidebar nav a').forEach(a=>{if(a.pathname===location.pathname)a.classList.add('active')});
document.querySelectorAll('form.confirm').forEach(f=>f.addEventListener('submit',e=>{
 if(f.dataset.confirmed==='1'){delete f.dataset.confirmed;return}
 e.preventDefault();const message=f.dataset.confirm||'Confirmar operação?';
 if(!window.bootstrap){if(confirm(message)){f.dataset.confirmed='1';f.requestSubmit(e.submitter)}return}
 const element=document.querySelector('#confirm-modal');const modal=bootstrap.Modal.getOrCreateInstance(element);
 document.querySelector('#confirm-message').textContent=message;
 document.querySelector('#confirm-accept').onclick=()=>{modal.hide();f.dataset.confirmed='1';f.requestSubmit(e.submitter)};
 modal.show()
}));
document.querySelector('#add-extra')?.addEventListener('click',()=>document.querySelector('#extras').append(document.querySelector('#extra-template').content.cloneNode(true)));
document.querySelectorAll('.part-form').forEach(f=>{
 const update=()=>{const s=f.querySelector('.part-select');if(!s)return;const selected=s.selectedOptions[0];const stock=Number(selected.dataset.stock);const qty=Number(f.querySelector('.part-qty').value);const feedback=f.querySelector('.stock-feedback');if(!s.value){feedback.textContent='';return}feedback.textContent=stock>=qty?'DISPONÍVEL':'ESTOQUE INSUFICIENTE - solicite a peça para o estoque';feedback.className='stock-feedback small '+(stock>=qty?'text-success':'text-danger')};
 f.addEventListener('change',update);f.addEventListener('input',update)
});

const machineSelect=document.querySelector('#machine-select');
const machineInfo=()=>{const option=machineSelect?.selectedOptions[0];if(!option)return;document.querySelector('#machine-summary').textContent=option.dataset.summary||'Selecione uma máquina';if(option.dataset.hours)document.querySelector('#entry-hours').value=option.dataset.hours};
machineSelect?.addEventListener('change',machineInfo);machineInfo();
document.querySelector('#machine-search')?.addEventListener('input',e=>{const query=e.target.value.toLowerCase();[...machineSelect.options].forEach(o=>{o.hidden=Boolean(o.value)&&!o.text.toLowerCase().includes(query)})});
document.querySelectorAll('.part-form').forEach(f=>f.dispatchEvent(new Event('change')));
