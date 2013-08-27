'use strict';

angular.module('pourOver').factory('Channels', function ($rootScope, ApiClient) {

  // ugly hack?
  $rootScope.channels = [];

  ApiClient.getBroadcastChannels({
    params: {
      include_annotations: 1
    }
  }).success(function (data) {
    $rootScope.channels = _.filter(data.data, function (channel) {
      return channel.you_subscribed;
    });
  });


  return {};
});