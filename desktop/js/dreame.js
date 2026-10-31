/* This file is part of the Jeedom "dreame" plugin (AGPL-3.0).
 * Page de gestion : bouton Synchroniser, recréation des commandes, tableau des commandes. */

$('#bt_dreameDiscover').on('click', function () {
  $.ajax({
    type: 'POST',
    url: 'plugins/dreame/core/ajax/dreame.ajax.php',
    data: { action: 'discover' },
    dataType: 'json',
    error: function (request, status, error) {
      handleAjaxError(request, status, error);
    },
    success: function (data) {
      if (data.state != 'ok') {
        $('#div_alert').showAlert({ message: data.result, level: 'danger' });
        return;
      }
      $('#div_alert').showAlert({ message: '{{Synchronisation en cours, la page va se recharger...}}', level: 'success' });
      setTimeout(function () { window.location.reload(); }, 8000);
    }
  });
});

$('#bt_dreameCreateCommands').on('click', function () {
  $.ajax({
    type: 'POST',
    url: 'plugins/dreame/core/ajax/dreame.ajax.php',
    data: { action: 'createCommands', id: $('.eqLogicAttr[data-l1key=id]').value() },
    dataType: 'json',
    error: function (request, status, error) {
      handleAjaxError(request, status, error);
    },
    success: function (data) {
      if (data.state != 'ok') {
        $('#div_alert').showAlert({ message: data.result, level: 'danger' });
        return;
      }
      $('.eqLogicDisplayCard[data-eqLogic_id=' + $('.eqLogicAttr[data-l1key=id]').value() + ']').click();
    }
  });
});

function addCmdToTable(_cmd) {
  if (!isset(_cmd)) {
    _cmd = { configuration: {} };
  }
  if (!isset(_cmd.configuration)) {
    _cmd.configuration = {};
  }
  let tr = '<tr class="cmd" data-cmd_id="' + init(_cmd.id) + '">';
  tr += '<td class="hidden-xs"><span class="cmdAttr" data-l1key="id"></span></td>';
  tr += '<td>';
  tr += '<div class="input-group">';
  tr += '<input class="cmdAttr form-control input-sm roundedLeft" data-l1key="name" placeholder="{{Nom de la commande}}">';
  tr += '<span class="input-group-btn"><a class="cmdAction btn btn-sm btn-default" data-l1key="chooseIcon" title="{{Choisir une icône}}"><i class="fas fa-icons"></i></a></span>';
  tr += '<span class="cmdAttr input-group-addon roundedRight" data-l1key="display" data-l2key="icon" style="font-size:19px;padding:0 5px 0 0!important;"></span>';
  tr += '</div>';
  tr += '</td>';
  tr += '<td>';
  tr += '<span class="type" type="' + init(_cmd.type) + '">' + jeedom.cmd.availableType() + '</span>';
  tr += '<span class="subType" subType="' + init(_cmd.subType) + '"></span>';
  tr += '</td>';
  tr += '<td><span class="cmdAttr" data-l1key="htmlstate"></span></td>';
  tr += '<td>';
  tr += '<label class="checkbox-inline"><input type="checkbox" class="cmdAttr" data-l1key="isVisible" checked>{{Afficher}}</label> ';
  if (_cmd.type == 'info') {
    tr += '<label class="checkbox-inline"><input type="checkbox" class="cmdAttr" data-l1key="isHistorized">{{Historiser}}</label> ';
    if (_cmd.subType == 'numeric' || _cmd.subType == 'binary') {
      tr += '<label class="checkbox-inline"><input type="checkbox" class="cmdAttr" data-l1key="display" data-l2key="invertBinary">{{Inverser}}</label>';
    }
  }
  tr += '<span class="cmdAttr" data-l1key="unite" style="margin-left:10px;"></span>';
  tr += '</td>';
  tr += '<td>';
  if (is_numeric(_cmd.id)) {
    tr += '<a class="btn btn-default btn-xs cmdAction" data-action="configure"><i class="fas fa-cogs"></i></a> ';
    tr += '<a class="btn btn-default btn-xs cmdAction" data-action="test"><i class="fas fa-rss"></i> {{Tester}}</a>';
  }
  tr += '</td>';
  tr += '</tr>';
  $('#table_cmd tbody').append(tr);
  const $tr = $('#table_cmd tbody tr').last();
  $tr.setValues(_cmd, '.cmdAttr');
  jeedom.cmd.changeType($tr, init(_cmd.subType));
  $tr.find('.cmdAttr[data-l1key=type],.cmdAttr[data-l1key=subType]').prop('disabled', true);
}
