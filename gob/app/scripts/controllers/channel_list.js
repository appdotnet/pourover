(function () {
  'use strict';

  angular.module('pourOver').controller('BroadcastChannelListCtrl', function (ApiClient, Channels, Auth, $scope) {
    window.location = 'https://directory.app.net/alerts/manage/';
  });
}());