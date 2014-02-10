'use strict';

(function () {
  var InstagramCtrl = function ($scope, $rootScope, $http, $location, Feeds) {
    $('#newFeedModal').modal('hide');
    console.log('yo dawg');
    var access_token = jQuery.url(window.location).fparam('access_token');
    if (access_token && window.opener) {
      window.opener.onInstagramAccessToken(access_token);
      window.close();
    }
    window.onInstagramAccessToken = function (accessToken) {
      $http.jsonp('https://api.instagram.com/v1/users/self/', {
        params: {
          'access_token': accessToken,
          'callback': 'JSON_CALLBACK'
        }
      }).success(function (resp) {
        $rootScope.feed = {
          feed_type: 2,
          access_token: access_token,
          username: resp.data.username,
          user_id: resp.data.id
        };

        Feeds.createFeed($rootScope.feed).then(function (feed) {
          $location.path('/feed/' + feed.feed_type + '/' + feed.feed_id);
        }, function () {
          window.alert('Something wen\'t wrong while saving your feed');
        });

      });
    }
  };

  InstagramCtrl.$inject = ['$scope', '$rootScope', '$http', '$location', 'Feeds'];
  angular.module('pourOver').controller('InstagramCtrl', InstagramCtrl);
})();
