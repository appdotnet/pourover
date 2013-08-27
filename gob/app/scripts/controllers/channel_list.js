(function () {
  'use strict';

  angular.module('pourOver').controller('BroadcastChannelListCtrl', function (ApiClient, Auth, $scope) {
    $scope.getChannelTitle = function (channel) {
      return ApiClient.getChannelMetadata(channel).title;
    };
  });
}());