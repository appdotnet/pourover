(function () {
  'use strict';

  angular.module('pourOver').controller('BroadcastChannelListCtrl', function (ApiClient, Channels, Auth, $scope) {
    $scope.getChannelTitle = function (channel) {
        return ApiClient.getChannelMetadata(channel).title;
    };
  });
}());